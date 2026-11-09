import 'dart:convert';

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import 'vault.dart';

enum RecordKind { patient, screening }

enum SyncState { pending, synced, error }

/// Patiente ou dépistage saisi sur l'appareil. Le contenu (`payload`) et le résultat sont chiffrés.
class LocalRecord {
  LocalRecord({
    required this.clientId,
    required this.kind,
    required this.payload,
    required this.createdAt,
    this.patientClientId,
    this.serverPatientId,
    this.pathology,
    this.state = SyncState.pending,
    this.serverId,
    this.error,
    this.result,
    this.alertCount = 0,
    this.syncedAt,
  });

  final String clientId;
  final RecordKind kind;
  /// Dépistage d'une patiente créée sur l'appareil
  final String? patientClientId;
  /// Dépistage d'une patiente déjà connue du serveur
  String? serverPatientId;
  final String? pathology;
  Map<String, dynamic> payload;
  SyncState state;
  String? serverId;
  String? error;
  /// Résultat de l'analyse récupéré après synchronisation
  Map<String, dynamic>? result;
  int alertCount;
  final DateTime createdAt;
  DateTime? syncedAt;
}

class LocalStore {
  LocalStore._(this._db, this._vault);

  final Database _db;
  final Vault _vault;

  static Future<LocalStore> open(Vault vault, {DatabaseFactory? factory, String? path}) async {
    final f = factory ?? databaseFactory;
    final dbPath = path ?? p.join(await f.getDatabasesPath(), 'cancerscan.db');
    final db = await f.openDatabase(dbPath, options: OpenDatabaseOptions(version: 1, onCreate: (db, _) async {
      await db.execute('CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
      await db.execute('''
        CREATE TABLE records (
          client_id TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          patient_client_id TEXT,
          server_patient_id TEXT,
          pathology TEXT,
          payload TEXT NOT NULL,
          state TEXT NOT NULL,
          server_id TEXT,
          error TEXT,
          result TEXT,
          alert_count INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          synced_at TEXT
        )''');
      await db.execute('CREATE INDEX idx_records_state ON records(state)');
    }));
    return LocalStore._(db, vault);
  }

  Future<void> close() => _db.close();

  // --- Valeurs simples (formulaires en cache, profil, URL du serveur) ------------------

  Future<void> putJson(String key, Object? value) =>
      _db.insert('kv', {'key': key, 'value': jsonEncode(value)}, conflictAlgorithm: ConflictAlgorithm.replace);

  Future<dynamic> getJson(String key) async {
    final rows = await _db.query('kv', where: 'key = ?', whereArgs: [key]);
    return rows.isEmpty ? null : jsonDecode(rows.first['value'] as String);
  }

  Future<void> deleteKey(String key) => _db.delete('kv', where: 'key = ?', whereArgs: [key]);

  // --- Enregistrements ----------------------------------------------------------------

  Future<void> save(LocalRecord r) async {
    await _db.insert(
      'records',
      {
        'client_id': r.clientId,
        'kind': r.kind.name,
        'patient_client_id': r.patientClientId,
        'server_patient_id': r.serverPatientId,
        'pathology': r.pathology,
        'payload': await _vault.encrypt(r.payload),
        'state': r.state.name,
        'server_id': r.serverId,
        'error': r.error,
        'result': r.result == null ? null : await _vault.encrypt(r.result!),
        'alert_count': r.alertCount,
        'created_at': r.createdAt.toIso8601String(),
        'synced_at': r.syncedAt?.toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<LocalRecord> _fromRow(Map<String, Object?> row) async => LocalRecord(
        clientId: row['client_id'] as String,
        kind: RecordKind.values.byName(row['kind'] as String),
        patientClientId: row['patient_client_id'] as String?,
        serverPatientId: row['server_patient_id'] as String?,
        pathology: row['pathology'] as String?,
        payload: await _vault.decrypt(row['payload'] as String),
        state: SyncState.values.byName(row['state'] as String),
        serverId: row['server_id'] as String?,
        error: row['error'] as String?,
        result: row['result'] == null ? null : await _vault.decrypt(row['result'] as String),
        alertCount: row['alert_count'] as int,
        createdAt: DateTime.parse(row['created_at'] as String),
        syncedAt: row['synced_at'] == null ? null : DateTime.parse(row['synced_at'] as String),
      );

  Future<List<LocalRecord>> _query({String? where, List<Object?>? args}) async {
    final rows = await _db.query('records', where: where, whereArgs: args, orderBy: 'created_at DESC');
    return [for (final r in rows) await _fromRow(r)];
  }

  Future<LocalRecord?> get(String clientId) async =>
      (await _query(where: 'client_id = ?', args: [clientId])).firstOrNull;

  Future<List<LocalRecord>> patients() => _query(where: 'kind = ?', args: ['patient']);

  Future<List<LocalRecord>> screenings() => _query(where: 'kind = ?', args: ['screening']);

  Future<List<LocalRecord>> screeningsOfLocalPatient(String patientClientId) =>
      _query(where: 'kind = ? AND patient_client_id = ?', args: ['screening', patientClientId]);

  Future<List<LocalRecord>> screeningsOfServerPatient(String serverPatientId) =>
      _query(where: 'kind = ? AND server_patient_id = ?', args: ['screening', serverPatientId]);

  Future<List<LocalRecord>> unsynced() => _query(where: 'state != ?', args: ['synced']);

  Future<int> pendingCount() async =>
      Sqflite.firstIntValue(await _db.rawQuery("SELECT COUNT(*) FROM records WHERE state != 'synced'")) ?? 0;

  /// Supprime les données de patientes synchronisées depuis plus de [days] jours (limitation de la conservation sur l'appareil).
  Future<int> purgeSynced({int days = 30}) {
    final limit = DateTime.now().subtract(Duration(days: days)).toIso8601String();
    return _db.delete('records', where: "state = 'synced' AND synced_at < ?", whereArgs: [limit]);
  }

  Future<void> wipe() async {
    await _db.delete('records');
    await _db.delete('kv');
  }
}
