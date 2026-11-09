import 'dart:convert';
import 'dart:io';

import 'package:cancerscan/core/api_client.dart';
import 'package:cancerscan/core/app_state.dart';
import 'package:cancerscan/core/form_logic.dart';
import 'package:cancerscan/core/local_store.dart';
import 'package:cancerscan/core/vault.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Réponse JSON encodée en UTF-8, comme l'API FastAPI.
http.Response json(Object body, [int status = 200]) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json; charset=utf-8'});

/// Faux serveur reproduisant le contrat de POST /sync (idempotence par client_uuid).
class FakeServer {
  final Map<String, String> known = {}; // client_uuid → server_id
  final List<Map<String, dynamic>> batches = [];
  final List<Map<String, dynamic>> errorReports = [];
  bool offline = false;
  String? rejectPatientPhone;
  int _seq = 0;

  String _id() => '00000000-0000-0000-0000-${(++_seq).toString().padLeft(12, '0')}';

  Map<String, dynamic> _item(Map<String, dynamic> x) {
    final cu = x['client_uuid'] as String;
    if (known.containsKey(cu)) return {'client_uuid': cu, 'server_id': known[cu], 'status': 'already_synced'};
    return {'client_uuid': cu, 'server_id': known[cu] = _id(), 'status': 'created'};
  }

  Future<http.Response> handle(http.Request req) async {
    if (offline) throw const SocketException('pas de réseau');
    if (req.url.path.endsWith('/sync')) {
      final body = jsonDecode(req.body) as Map<String, dynamic>;
      batches.add(body);
      final patients = [], screenings = [];
      for (final p in body['patients'] as List) {
        if (rejectPatientPhone != null && p['phone'] == rejectPatientPhone) {
          patients.add({'client_uuid': p['client_uuid'], 'status': 'error', 'detail': 'Données invalides'});
          continue;
        }
        patients.add(_item(p));
        for (final s in p['screenings'] as List) {
          screenings.add(_item(s));
        }
      }
      for (final s in body['screenings'] as List) {
        screenings.add(_item(s));
      }
      return json({'patients': patients, 'screenings': screenings});
    }
    if (req.url.path.contains('/screenings/')) {
      return json({
        'id': req.url.pathSegments.last,
        'patient_id': 'srv-patient',
        'status': 'analyse',
        'assessments': [
          {'risk_level': 'eleve', 'score': 0.81, 'model_validated': false, 'model_id': 'sein-test', 'model_version': '1', 'explanations': []}
        ],
        'referral': {'proposed_level': 'eleve', 'proposed_recommendation': 'Référence prioritaire', 'final_decision': null, 'status': 'proposee'},
      });
    }
    if (req.url.path.endsWith('/client-errors')) {
      if (offline) throw const SocketException('pas de réseau');
      errorReports.add(jsonDecode(req.body) as Map<String, dynamic>);
      return json({'id': errorReports.length}, 202);
    }
    if (req.url.path.endsWith('/forms')) return json([]);
    return http.Response('{"detail":"inconnu"}', 404);
  }
}

void main() {
  sqfliteFfiInit();
  late FakeServer server;
  late LocalStore store;
  late AppState app;
  late String dbPath;
  final sein = FormDef.fromJson(jsonDecode(File('../shared/forms/sein.json').readAsStringSync()) as Map<String, dynamic>);
  final data = <String, Object?>{
    'atcd_familial_sein_ovaire': false,
    'atcd_personnel_sein': false,
    'masse_presente': true,
    'modif_peau': false,
    'retraction_mamelon': true,
    'examen_realise': false,
    'probabilite_enqueteur': 'elevee',
  };

  setUp(() async {
    server = FakeServer();
    final keys = MemoryKeyStore();
    // Une base fichier par test : aucun état partagé entre les tests
    dbPath = '${Directory.systemTemp.createTempSync('cancerscan_test').path}/test.db';
    store = await LocalStore.open(await Vault.open(keys), factory: databaseFactoryFfi, path: dbPath);
    final api = ApiClient(baseUrl: 'http://serveur/api/v1', client: MockClient(server.handle))..token = 't';
    app = AppState(store: store, api: api, keyStore: keys)..user = {'id': 1};
  });

  tearDown(() async {
    await app.idle; // laisse se terminer la synchronisation automatique déclenchée par une saisie
    await store.close();
  });

  test('saisie hors ligne puis synchronisation au retour du réseau', () async {
    server.offline = true;
    final p = await app.createPatient({'full_name': 'Afi', 'region': 'Maritime', 'consent_given': true});
    final s = await app.createScreening(form: sein, data: data, patientClientId: p.clientId);
    await app.idle; // la synchronisation automatique échoue : hors ligne
    expect(app.online, isFalse);
    expect(await store.pendingCount(), 2);
    expect((await store.get(s.clientId))!.alertCount, 2);

    server.offline = false;
    final report = await app.syncNow();
    expect(report!.created, 2);
    expect(await store.pendingCount(), 0);
    // Le dépistage est envoyé avec sa patiente
    final patientsSent = server.batches.last['patients'] as List;
    expect((patientsSent.single['screenings'] as List).single['client_uuid'], s.clientId);
    // Le résultat de l'analyse est récupéré et conservé (chiffré) sur l'appareil
    final synced = await store.get(s.clientId);
    expect(synced!.result!['risk_level'], 'eleve');
  });

  test('renvoyer un lot ne crée pas de doublon', () async {
    final p = await app.createPatient({'region': 'Kara', 'consent_given': true});
    // Simule une réponse perdue : le serveur a reçu la patiente mais l'appareil l'ignore
    server.known[p.clientId] = 'srv-1';
    final report = await app.sync.run();
    expect(report.alreadySynced, 1);
    expect((await store.get(p.clientId))!.serverId, 'srv-1');
  });

  test('un dépistage pour une patiente du serveur est envoyé avec son identifiant', () async {
    final s = await app.createScreening(form: sein, data: data, serverPatientId: 'srv-patient', patientLabel: 'Ama');
    await app.idle; // la saisie déclenche une synchronisation automatique
    final sent = (server.batches.last['screenings'] as List).single as Map;
    expect(sent['patient_id'], 'srv-patient');
    expect(sent.containsKey('patient_label'), isFalse); // le libellé reste sur l'appareil
    expect((await store.get(s.clientId))!.state, SyncState.synced);
  });

  test('une patiente refusée bloque ses dépistages sans bloquer les autres', () async {
    server.rejectPatientPhone = '000';
    final bad = await app.createPatient({'region': 'Kara', 'phone': '000', 'consent_given': true});
    final badScreening = await app.createScreening(form: sein, data: data, patientClientId: bad.clientId);
    await app.idle; // synchronisation automatique déclenchée par le dépistage
    final good = await app.createPatient({'region': 'Kara', 'consent_given': true});
    final report = (await app.syncNow())!;
    expect(report.errors, 1); // la patiente refusée est retentée à chaque synchronisation…
    expect(report.created, 1); // …sans bloquer l'envoi des autres
    expect((await store.get(bad.clientId))!.state, SyncState.error);
    expect((await store.get(badScreening.clientId))!.state, SyncState.error);
    expect((await store.get(good.clientId))!.state, SyncState.synced);
  });

  test('les données des patientes sont chiffrées dans la base locale', () async {
    final p = await app.createPatient({'full_name': 'Afi Mensah', 'phone': '+228 90 00 00 01', 'region': 'Maritime', 'consent_given': true});
    final db = await databaseFactoryFfi.openDatabase(dbPath, options: OpenDatabaseOptions(singleInstance: false));
    final raw = await db.query('records', where: 'client_id = ?', whereArgs: [p.clientId]);
    expect(raw.single['payload'], isNot(contains('Afi')));
    expect((await store.get(p.clientId))!.payload['full_name'], 'Afi Mensah');
  });

  test('session expirée : les saisies restent sur l\'appareil', () async {
    final api = ApiClient(baseUrl: 'http://serveur/api/v1', client: MockClient((_) async => http.Response('{"detail":"x"}', 401)));
    final expired = AppState(store: store, api: api, keyStore: MemoryKeyStore())..user = {'id': 1};
    await expired.createPatient({'region': 'Kara', 'consent_given': true});
    await expired.syncNow(silent: true);
    expect(expired.needsLogin, isTrue);
    expect(await store.pendingCount(), 1);
  });

  test("les erreurs de l'application sont mises en file hors ligne puis envoyées à la synchronisation", () async {
    server.offline = true;
    await app.errors.report(StateError('panne simulée'), StackTrace.current, screen: 'wizard');
    await app.errors.report(StateError('panne simulée'), StackTrace.current); // doublon ignoré
    expect(await app.errors.pending(), 1);
    await app.syncNow(silent: true);
    expect(await app.errors.pending(), 1); // toujours hors ligne : conservée

    server.offline = false;
    await app.syncNow();
    expect(await app.errors.pending(), 0);
    expect(server.errorReports.single['message'], contains('panne simulée'));
    expect(server.errorReports.single['source'], 'mobile');
    expect(server.errorReports.single.containsKey('time'), isFalse);
  });
}
