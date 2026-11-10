import 'api_client.dart';
import 'local_store.dart';

class SyncReport {
  int sent = 0;
  int created = 0;
  int alreadySynced = 0;
  int errors = 0;
  int resultsFetched = 0;
  final List<String> messages = [];

  bool get hasErrors => errors > 0;
  @override
  String toString() =>
      'envoyés $sent · créés $created · déjà reçus $alreadySynced · erreurs $errors · résultats $resultsFetched';
}

/// Envoie la file d'attente locale à POST /sync puis récupère les résultats d'analyse.
///
/// Idempotent : chaque élément porte son `client_uuid`, le serveur ignore ce qu'il a déjà reçu.
/// Une erreur sur un élément n'empêche pas la synchronisation des autres.
class SyncService {
  SyncService(this.api, this.store);

  final ApiClient api;
  final LocalStore store;

  Map<String, Object?> _screeningItem(LocalRecord s) => {
        'client_uuid': s.clientId,
        'pathology': s.pathology,
        'data': s.payload['data'],
        'submit': s.payload['submit'] ?? true,
      };

  Future<SyncReport>? _running;

  /// Lance une synchronisation. [OfflineException] si le serveur est injoignable,
  /// [ApiException] 401 si la session doit être renouvelée.
  /// Jamais deux synchronisations en parallèle : un appel pendant un envoi attend le résultat de celui-ci
  /// (deux envois simultanés se gênaient côté serveur et pouvaient faire perdre le résultat de l'analyse).
  Future<SyncReport> run() => _running ??= _run().whenComplete(() => _running = null);

  Future<SyncReport> _run() async {
    final report = SyncReport();
    final pending = await store.unsynced();
    final byId = {for (final r in await store.patients()) r.clientId: r};

    final patientsOut = <Map<String, Object?>>[];
    final screeningsOut = <Map<String, Object?>>[];
    final nestedOf = <String, List<LocalRecord>>{};

    for (final p in pending.where((r) => r.kind == RecordKind.patient)) {
      final nested = pending.where((s) => s.kind == RecordKind.screening && s.patientClientId == p.clientId).toList();
      nestedOf[p.clientId] = nested;
      patientsOut.add({...p.payload, 'client_uuid': p.clientId, 'screenings': [for (final s in nested) _screeningItem(s)]});
    }
    for (final s in pending.where((r) => r.kind == RecordKind.screening)) {
      if (s.patientClientId != null && nestedOf.containsKey(s.patientClientId)) continue; // envoyé avec sa patiente
      // Patiente connue du serveur, ou créée sur l'appareil et déjà synchronisée
      final patientId = s.serverPatientId ?? byId[s.patientClientId]?.serverId;
      if (patientId == null) continue; // patiente locale pas encore synchronisée (ex. en erreur)
      screeningsOut.add({..._screeningItem(s), 'patient_id': patientId});
    }

    if (patientsOut.isNotEmpty || screeningsOut.isNotEmpty) {
      report.sent = patientsOut.length + screeningsOut.length;
      final res = await api.sync({'patients': patientsOut, 'screenings': screeningsOut});
      final results = {
        for (final item in [...(res['patients'] as List), ...(res['screenings'] as List)])
          (item as Map<String, dynamic>)['client_uuid'] as String: item,
      };
      final now = DateTime.now();

      for (final r in pending) {
        final item = results[r.clientId];
        if (item == null) continue;
        final status = item['status'] as String;
        if (status == 'error') {
          r
            ..state = SyncState.error
            ..error = item['detail'] as String? ?? 'Erreur de synchronisation';
          report.errors++;
          report.messages.add(r.error!);
        } else {
          r
            ..state = SyncState.synced
            ..serverId = item['server_id'] as String?
            ..error = null
            ..syncedAt = now;
          status == 'created' ? report.created++ : report.alreadySynced++;
        }
        await store.save(r);
      }
      // Dépistages d'une patiente refusée par le serveur : ils n'ont pas été traités
      for (final entry in nestedOf.entries) {
        final patient = await store.get(entry.key);
        if (patient?.state != SyncState.error) continue;
        for (final s in entry.value.where((s) => results[s.clientId] == null)) {
          s
            ..state = SyncState.error
            ..error = 'Patiente non synchronisée : ${patient!.error}';
          await store.save(s);
        }
      }
    }

    report.resultsFetched = await fetchResults();
    return report;
  }

  /// Récupère le résultat d'analyse des dépistages synchronisés dont l'analyse n'est pas encore connue
  /// (ou était en attente côté serveur).
  Future<int> fetchResults() async {
    var count = 0;
    for (final s in await store.screenings()) {
      if (s.state != SyncState.synced || s.serverId == null) continue;
      final known = s.result?['status'];
      if (known != null && known != 'soumis') continue; // seul « soumis » (analyse IA différée) peut encore évoluer
      final remote = await api.screening(s.serverId!);
      s.result = summarize(remote);
      s.serverPatientId ??= remote['patient_id'] as String?;
      await store.save(s);
      count++;
    }
    return count;
  }

  /// Résumé conservé sur l'appareil (le dossier complet reste sur le serveur).
  static Map<String, Object?> summarize(Map<String, dynamic> screening) {
    final assessments = screening['assessments'] as List? ?? [];
    final a = assessments.isEmpty ? null : assessments.first as Map<String, dynamic>;
    final ref = screening['referral'] as Map<String, dynamic>?;
    return {
      'status': screening['status'],
      'risk_level': a?['risk_level'],
      'score': a?['score'],
      'model_validated': a?['model_validated'],
      'model': a == null ? null : '${a['model_id']} v${a['model_version']}',
      'explanations': [for (final e in (a?['explanations'] as List? ?? []).take(3)) e],
      'proposed_level': ref?['proposed_level'],
      'recommendation': ref?['proposed_recommendation'],
      'final_decision': ref?['final_decision'],
      'referral_status': ref?['status'],
      'appointment_date': ref?['appointment_date'],
      // Structures spécialisées les plus proches (risque moyen ou élevé), pour orienter la patiente
      'suggested_facilities': [for (final f in (ref?['suggested_facilities'] as List? ?? [])) f],
      'to_facility_id': ref?['to_facility_id'],
    };
  }
}
