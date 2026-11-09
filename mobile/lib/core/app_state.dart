import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import 'api_client.dart';
import 'error_reporter.dart';
import 'form_logic.dart';
import 'local_store.dart';
import 'sync_service.dart';
import 'vault.dart';

/// URL par défaut : 10.0.2.2 est l'ordinateur hôte vu depuis l'émulateur Android.
const defaultApiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000/api/v1');

const _tokenKey = 'cancerscan.token';

/// État global : session, formulaires en cache, file d'attente et synchronisation.
class AppState extends ChangeNotifier {
  AppState({required this.store, required this.api, required this.keyStore, Stream<List<ConnectivityResult>>? connectivity})
      : sync = SyncService(api, store),
        errors = ErrorReporter(api, store) {
    _connSub = connectivity?.listen((results) {
      if (results.any((r) => r != ConnectivityResult.none)) unawaited(syncNow(silent: true));
    });
  }

  final LocalStore store;
  final ApiClient api;
  final KeyStore keyStore;
  final SyncService sync;
  final ErrorReporter errors;
  StreamSubscription<List<ConnectivityResult>>? _connSub;
  static const _uuid = Uuid();

  Map<String, dynamic>? user;
  List<String> permissions = [];
  Map<String, FormDef> forms = {};
  int pendingCount = 0;
  bool syncing = false;
  bool needsLogin = false;
  DateTime? lastSync;
  String? lastSyncMessage;
  bool online = true;
  /// Dernière synchronisation refusée par le serveur (erreur 5xx) : distinct d'une absence de réseau
  bool serverError = false;

  bool get isLoggedIn => user != null;
  bool can(String perm) => permissions.contains(perm);

  /// Le sein est la pathologie prioritaire de la première version.
  List<FormDef> get orderedForms => [
        for (final p in const ['sein', 'col', 'ovaire', 'endometre'])
          if (forms[p] != null) forms[p]!,
      ];

  /// Restaure la session et les formulaires depuis l'appareil (fonctionne hors ligne).
  Future<void> restore() async {
    api.baseUrl = (await store.getJson('api_url') as String?) ?? defaultApiUrl;
    api.token = await keyStore.read(_tokenKey);
    final cachedUser = await store.getJson('user');
    if (cachedUser != null && api.token != null) {
      user = Map<String, dynamic>.from(cachedUser['user'] as Map);
      permissions = List<String>.from(cachedUser['permissions'] as List);
    }
    _setForms(await store.getJson('forms') as List?);
    final last = await store.getJson('last_sync') as String?;
    lastSync = last == null ? null : DateTime.parse(last);
    await refreshPending();
    notifyListeners();
  }

  void _setForms(List? raw) {
    if (raw == null) return;
    forms = {for (final f in raw) (f as Map<String, dynamic>)['pathology'] as String: FormDef.fromJson(f)};
  }

  Future<void> setServerUrl(String url) async {
    api.baseUrl = url.trim().replaceAll(RegExp(r'/+$'), '');
    await store.putJson('api_url', api.baseUrl);
  }

  /// Première connexion obligatoirement en ligne ; les formulaires sont alors mis en cache.
  Future<void> login(String email, String password) async {
    final res = await api.login(email, password);
    final previousToken = api.token;
    api.token = res['access_token'] as String;
    final me = await api.me();
    final previousId = (await store.getJson('user'))?['user']?['id'];
    final newId = (me['user'] as Map)['id'];
    if (previousId != null && previousId != newId) {
      // Les saisies non envoyées du compte précédent partiraient sous un autre nom : on refuse.
      if (await store.pendingCount() > 0) {
        api.token = previousToken;
        throw ApiException(409, 'Des saisies du compte précédent ne sont pas synchronisées : reconnectez-vous avec ce compte pour les envoyer.');
      }
      await store.wipe(); // un autre compte ne voit pas les données du précédent
      await store.putJson('api_url', api.baseUrl);
    }
    await keyStore.write(_tokenKey, api.token!);
    user = Map<String, dynamic>.from(me['user'] as Map);
    permissions = List<String>.from(me['permissions'] as List);
    await store.putJson('user', me);
    await refreshForms();
    needsLogin = false;
    online = true;
    notifyListeners();
    unawaited(syncNow(silent: true));
  }

  Future<void> refreshForms() async {
    final raw = await api.forms();
    await store.putJson('forms', raw);
    _setForms(raw);
  }

  /// Déconnexion. Refusée tant que des saisies ne sont pas synchronisées, pour ne pas les perdre.
  Future<bool> logout({bool force = false}) async {
    if (!force && await store.pendingCount() > 0) return false;
    await keyStore.delete(_tokenKey);
    api.token = null;
    user = null;
    permissions = [];
    await store.wipe();
    notifyListeners();
    return true;
  }

  Future<void> refreshPending() async {
    pendingCount = await store.pendingCount();
    notifyListeners();
  }

  // --- Saisie (toujours locale d'abord) ---------------------------------------------

  Future<LocalRecord> createPatient(Map<String, Object?> fields) async {
    final r = LocalRecord(clientId: _uuid.v4(), kind: RecordKind.patient, payload: fields, createdAt: DateTime.now());
    await store.save(r);
    await refreshPending();
    return r;
  }

  /// [patientClientId] pour une patiente créée sur l'appareil, [serverPatientId] pour une patiente du serveur.
  Future<LocalRecord> createScreening({
    required FormDef form,
    required Map<String, Object?> data,
    String? patientClientId,
    String? serverPatientId,
    String? patientLabel,
  }) async {
    final check = checkForm(form, data);
    if (!check.isComplete) throw StateError('Formulaire incomplet');
    final r = LocalRecord(
      clientId: _uuid.v4(),
      kind: RecordKind.screening,
      patientClientId: patientClientId,
      serverPatientId: serverPatientId,
      pathology: form.pathology,
      payload: {
        'data': check.cleaned,
        'submit': true,
        'form_version': form.version,
        'alerts': [for (final f in check.alerts) f.label],
        // Libellé affiché sur l'appareil uniquement (chiffré, jamais envoyé avec le dépistage)
        'patient_label': patientLabel,
      },
      alertCount: check.alerts.length,
      createdAt: DateTime.now(),
    );
    await store.save(r);
    await refreshPending();
    unawaited(syncNow(silent: true));
    return r;
  }

  // --- Synchronisation --------------------------------------------------------------

  Future<SyncReport>? _inFlight;

  /// Termine quand aucune synchronisation n'est en cours (utile après une saisie, qui en déclenche une).
  Future<void> get idle async {
    try {
      await _inFlight;
    } catch (_) {/* l'erreur a déjà été reflétée dans l'état */}
  }

  /// Synchronise maintenant. Si une synchronisation est déjà en cours (ex. automatique), on attend son
  /// résultat au lieu d'en lancer une seconde. En mode [silent], les erreurs sont reflétées dans l'état
  /// (`online`, `needsLogin`, `lastSyncMessage`) sans être relancées.
  Future<SyncReport?> syncNow({bool silent = false}) async {
    if (!isLoggedIn) return null;
    final running = _inFlight ??= _runSync().whenComplete(() => _inFlight = null);
    try {
      return await running;
    } on OfflineException {
      if (!silent) rethrow;
    } on ApiException {
      if (!silent) rethrow;
    }
    return null;
  }

  Future<SyncReport> _runSync() async {
    syncing = true;
    notifyListeners();
    try {
      final report = await sync.run();
      online = true;
      needsLogin = false;
      serverError = false;
      lastSync = DateTime.now();
      await store.putJson('last_sync', lastSync!.toIso8601String());
      await store.purgeSynced();
      lastSyncMessage = report.hasErrors ? 'Synchronisation partielle : ${report.messages.first}' : 'Synchronisé';
      try {
        await refreshForms();
      } catch (_) {/* les formulaires en cache restent utilisables */}
      try {
        await errors.flush(); // rapports d'erreurs mis en file pendant le travail hors ligne
      } catch (_) {}
      return report;
    } on OfflineException {
      online = false;
      lastSyncMessage = 'Hors ligne : les saisies seront envoyées au retour de la connexion';
      rethrow;
    } on ApiException catch (e) {
      if (e.isUnauthorized) needsLogin = true;
      // Erreur du serveur : on reste « en ligne », les saisies restent sur le téléphone et repartiront.
      lastSyncMessage = e.status >= 500 ? "Le serveur n'a pas pu traiter l'envoi : nouvel essai automatique." : e.message;
      serverError = e.status >= 500;
      rethrow;
    } finally {
      syncing = false;
      await refreshPending();
    }
  }

  @override
  void dispose() {
    _connSub?.cancel();
    super.dispose();
  }
}
