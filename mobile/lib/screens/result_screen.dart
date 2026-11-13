import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api_client.dart';
import '../core/app_state.dart';
import '../core/form_logic.dart';
import '../core/local_store.dart';
import '../theme.dart';
import '../widgets/form_renderer.dart';
import '../widgets/referral_places.dart';
import '../widgets/ui.dart';
import 'wizard_screen.dart';

/// Résultat d'un dépistage. Le niveau affiché vient toujours du serveur (score calibré + seuils) :
/// il n'existe pas de « risque faible » avec un score élevé. Sans connexion, l'écran l'indique clairement.
class ResultScreen extends StatefulWidget {
  const ResultScreen({super.key, required this.clientId});
  final String clientId;
  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  LocalRecord? _record;
  LocalRecord? _patient;
  Timer? _retry;
  int _attempts = 0;
  Map<String, Object?>? _notes;
  bool _savingNotes = false;

  @override
  void initState() {
    super.initState();
    _load();
    context.read<AppState>().addListener(_load);
    // Tant que le résultat de l'IA n'est pas arrivé, on retente tout seul (sans action de l'agent).
    _retry = Timer.periodic(const Duration(seconds: 15), (_) => _retryIfPending());
  }

  @override
  void dispose() {
    _retry?.cancel();
    context.read<AppState>().removeListener(_load);
    super.dispose();
  }

  void _retryIfPending() {
    final app = context.read<AppState>();
    final analysed = _record?.result?['risk_level'] != null;
    if (!mounted || analysed || _attempts >= 12) {
      if (analysed || _attempts >= 12) _retry?.cancel();
      return;
    }
    if (!app.syncing) {
      _attempts++;
      unawaited(app.syncNow(silent: true));
    }
  }

  /// Appréciation de l'agent, donnée après le résultat : envoyée directement au serveur (sans relancer l'analyse).
  Future<void> _saveNotes(LocalRecord r) async {
    final app = context.read<AppState>();
    setState(() => _savingNotes = true);
    try {
      await app.api.saveAgentNotes(r.serverId!, _notes ?? {});
      r.payload['agent_notes'] = _notes;
      await app.store.save(r);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Appréciation enregistrée')));
    } on OfflineException {
      if (mounted) showError(context, 'Connexion nécessaire pour enregistrer votre appréciation.');
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _savingNotes = false);
    }
  }

  Future<void> _load() async {
    final store = context.read<AppState>().store;
    final r = await store.get(widget.clientId);
    final p = r?.patientClientId == null ? null : await store.get(r!.patientClientId!);
    if (mounted) {
      setState(() {
        _record = r;
        _patient = p;
      });
    }
  }

  String _answer(AppState app, String? pathology, String feature, Object? value) {
    if (value == null || value == 'inconnu') return 'non renseigné';
    if (feature == 'age') return '$value ans';
    final field = app.forms[pathology]?.field(feature);
    return field == null ? '$value' : displayValue(field, value);
  }

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final r = _record;
    if (r == null) return Scaffold(appBar: AppBar(title: const Text('Résultat de l\'Analyse')), body: const Center(child: CircularProgressIndicator()));

    final res = r.result ?? const <String, dynamic>{};
    final level = res['risk_level'] as String?;
    final alerts = List<String>.from(r.payload['alerts'] as List? ?? []);
    final analysed = level != null;
    final (color, icon, label) = riskStyle(level);

    return Scaffold(
      appBar: AppBar(title: const Text('Résultat de l\'Analyse'), automaticallyImplyLeading: false),
      body: RefreshIndicator(
        onRefresh: () async => app.syncNow(silent: true),
        child: ListView(padding: const EdgeInsets.fromLTRB(16, 18, 16, 28), children: [
          // --- Grande carte du niveau de risque (dégradé + anneau de score animé) --------
          Container(
            padding: const EdgeInsets.fromLTRB(20, 26, 20, 22),
            decoration: BoxDecoration(
              gradient: AppColors.gradientOf(color),
              borderRadius: BorderRadius.circular(28),
              boxShadow: [BoxShadow(color: color.withValues(alpha: 0.35), blurRadius: 24, offset: const Offset(0, 10))],
            ),
            child: Column(children: [
              Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                Icon(icon, color: Colors.white, size: 30),
                const SizedBox(width: 10),
                Flexible(child: Text(label, style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w800))),
              ]),
              const SizedBox(height: 18),
              if (analysed && res['score'] != null)
                ScoreRing(score: (res['score'] as num).toDouble())
              else
                Container(
                  width: 150,
                  height: 150,
                  decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: Colors.white38, width: 12)),
                  child: Center(
                    child: app.syncing
                        ? const SizedBox(width: 40, height: 40, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 3))
                        : const Icon(Icons.cloud_upload_rounded, color: Colors.white, size: 52),
                  ),
                ),
              const SizedBox(height: 14),
              Text(
                analysed ? 'Niveau déterminé par le score calibré du modèle' : (app.syncing ? 'Analyse en cours…' : 'Sera calculée à la synchronisation'),
                style: const TextStyle(color: Colors.white, fontSize: 14.5),
              ),
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.16), borderRadius: BorderRadius.circular(999)),
                child: SyncBadge(r.state),
              ),
            ]),
          ),
          const SizedBox(height: 18),
          if (analysed && res['model_validated'] != true)
            const Notice(kind: NoticeKind.warning, title: 'Modèle non validé cliniquement', text: 'Résultat de démonstration : il ne doit pas guider seul une décision médicale.'),
          if (alerts.isNotEmpty)
            Notice(
              kind: NoticeKind.danger,
              title: 'Signe(s) d\'alerte',
              text: '${alerts.join(' · ')}.\nUne évaluation médicale est nécessaire, même si le risque estimé est faible.',
            ),
          if (r.state == SyncState.error) Notice(kind: NoticeKind.danger, title: 'Envoi refusé par le serveur', text: r.error ?? ''),
          if (!analysed && r.state != SyncState.error)
            Notice(
              kind: NoticeKind.warning,
              title: 'Analyse IA non encore calculée',
              text: r.state == SyncState.pending
                  ? (!app.online
                      ? 'Pas de connexion : le dépistage est enregistré sur le téléphone. Il sera envoyé et analysé dès le retour du réseau.'
                      : app.serverError
                          ? "Le serveur n'a pas pu traiter l'envoi. Nouvel essai automatique dans quelques secondes ; le dépistage reste sur le téléphone."
                          : 'Envoi au serveur et analyse en cours…')
                  : "Le serveur n'a pas encore produit de résultat (moteur IA indisponible ou modèle non déployé). Nouvel essai automatique.",
              action: OutlinedButton.icon(
                onPressed: app.syncing ? null : () => app.syncNow(silent: true),
                icon: const Icon(Icons.sync),
                label: const Text('Synchroniser maintenant'),
              ),
            ),

          // --- Informations patient ------------------------------------------------------
          InfoCard(
            icon: Icons.person,
            title: 'Informations Patient',
            children: [
              for (final (k, v) in _patientRows(r)) KeyValue(k, v),
            ],
          ),

          // --- Recommandations -----------------------------------------------------------
          InfoCard(
            icon: Icons.assignment,
            iconColor: color,
            title: 'Recommandations',
            children: [
              Text(
                analysed
                    ? '${res['recommendation'] ?? ''}'
                    : alerts.isNotEmpty
                        ? 'En attendant l\'analyse : orienter la patiente vers une évaluation médicale en raison des signes d\'alerte.'
                        : 'En attendant l\'analyse : conseiller l\'auto-examen des seins et une consultation en cas de nouveau symptôme.',
                style: const TextStyle(fontSize: 16, height: 1.4),
              ),
            ],
          ),

          // --- Facteurs (explications) -------------------------------------------------
          if (analysed && (res['explanations'] as List? ?? []).isNotEmpty)
            InfoCard(
              icon: Icons.insights,
              title: 'Facteurs ayant le plus pesé',
              children: [
                for (final e in res['explanations'] as List)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Icon((e['contribution'] as num) > 0 ? Icons.arrow_upward : Icons.arrow_downward,
                          color: (e['contribution'] as num) > 0 ? AppColors.eleve : AppColors.faible),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text.rich(TextSpan(children: [
                          TextSpan(text: '${e['label'] ?? e['feature']}', style: const TextStyle(fontSize: 15)),
                          // La réponse saisie accompagne toujours le facteur (jamais de contribution hors contexte)
                          if ((e as Map).containsKey('value'))
                            TextSpan(text: ' : ${_answer(app, r.pathology, e['feature'] as String, e['value'])}', style: const TextStyle(fontWeight: FontWeight.w700)),
                        ])),
                      ),
                    ]),
                  ),
                const SizedBox(height: 4),
                const Text('Ces facteurs décrivent le fonctionnement du modèle ; ils ne prouvent pas une cause.', style: TextStyle(fontSize: 12, color: Colors.black54)),
              ],
            ),

          // --- Orientation ---------------------------------------------------------------
          _OrientationCard(level: analysed ? res['proposed_level'] as String? : (alerts.isNotEmpty ? 'moyen' : null), result: res, pending: !analysed),

          // --- Où orienter la patiente : structures spécialisées les plus proches ----------
          if (analysed && (res['suggested_facilities'] as List? ?? []).isNotEmpty)
            ReferralPlacesCard(
              level: res['proposed_level'] as String?,
              places: [for (final f in res['suggested_facilities'] as List) Map<String, dynamic>.from(f as Map)],
              chosenId: res['to_facility_id'] as int?,
              decided: res['final_decision'] != null,
            ),

          // --- Appréciation de l'agent : seulement APRÈS le résultat de l'IA ---------------
          // Plus modifiable une fois l'orientation validée par un professionnel
          if (analysed && r.serverId != null && app.forms[r.pathology] != null && res['status'] != 'valide' && res['final_decision'] == null) ...[
            for (final section in app.forms[r.pathology]!.sections.where((s) => s.fields.any((f) => f.afterResult)))
              InfoCard(
                icon: Icons.psychology_alt_rounded,
                title: 'Votre appréciation',
                children: [
                  const Text('Après avoir pris connaissance du résultat, donnez votre appréciation clinique et les conseils donnés.',
                      style: TextStyle(color: Colors.black54, fontSize: 14)),
                  const SizedBox(height: 14),
                  SectionFields(
                    section: section,
                    afterResult: true,
                    data: _notes ??= Map<String, Object?>.from(r.payload['agent_notes'] as Map? ?? {}),
                    errors: const {},
                    onChanged: (id, v) => setState(() => v == null ? _notes!.remove(id) : _notes![id] = v),
                  ),
                  FilledButton.icon(
                    onPressed: _savingNotes ? null : () => _saveNotes(r),
                    icon: const Icon(Icons.check_rounded),
                    label: Text(_savingNotes ? 'Enregistrement…' : 'Enregistrer mon appréciation'),
                  ),
                ],
              ),
          ],

          const SizedBox(height: 8),
          const Text('Un risque faible ne signifie jamais qu\'un cancer est absent. Le diagnostic relève des professionnels de santé.',
              textAlign: TextAlign.center, style: TextStyle(fontSize: 12, color: Colors.black54)),
          const SizedBox(height: 18),
          Row(children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const WizardScreen())),
                icon: const Icon(Icons.add),
                label: const Text('Nouveau'),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: FilledButton.icon(
                onPressed: () => Navigator.of(context).popUntil((route) => route.isFirst),
                icon: const Icon(Icons.home),
                label: const Text('Accueil'),
              ),
            ),
          ]),
        ]),
      ),
    );
  }

  List<(String, String)> _patientRows(LocalRecord r) {
    final p = _patient?.payload;
    final year = p?['birth_year_estimated'] as int?;
    return [
      if (p != null) ...[
        if (p['full_name'] != null) ('Nom', '${p['full_name']}'),
        ('Âge', year != null ? '${r.createdAt.year - year} ans' : '—'),
        ('Localité', [p['locality'], p['region']].whereType<String>().join(', ')),
      ] else
        ('Patiente', '${r.payload['patient_label'] ?? '—'}'),
      ('Dépistage', pathologyLabels[r.pathology] ?? '${r.pathology}'),
      ('Date', formatDate(r.createdAt)),
    ];
  }
}

class _OrientationCard extends StatelessWidget {
  const _OrientationCard({required this.level, required this.result, required this.pending});
  final String? level;
  final Map<String, dynamic>? result;
  final bool pending;

  @override
  Widget build(BuildContext context) {
    final (color, _, _) = riskStyle(level);
    final (icon, title) = switch (level) {
      'eleve' => (Icons.local_hospital, 'Référence prioritaire vers un spécialiste'),
      'moyen' => (Icons.event, 'Rendez-vous de consultation spécialisée'),
      'faible' => (Icons.visibility, 'Surveillance simple\nAuto-examen mensuel recommandé'),
      _ => (Icons.hourglass_top, 'À définir après l\'analyse'),
    };
    final decision = result?['final_decision'] as String?;
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(16), border: Border.all(color: color.withValues(alpha: 0.4))),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          width: 60,
          height: 60,
          decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(14)),
          child: Icon(icon, color: Colors.white, size: 32),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('ORIENTATION${pending && level != null ? ' (signes d\'alerte)' : ''}',
                style: TextStyle(color: color, fontWeight: FontWeight.w800, letterSpacing: 0.5)),
            const SizedBox(height: 4),
            Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Text(
              decision != null
                  ? 'Décision du professionnel : $decision${result?['appointment_date'] != null ? '\nRendez-vous : ${result!['appointment_date']}' : ''}'
                  : 'Proposition à valider par un médecin ou un spécialiste.',
              style: const TextStyle(fontSize: 14, color: Colors.black87),
            ),
          ]),
        ),
      ]),
    );
  }
}
