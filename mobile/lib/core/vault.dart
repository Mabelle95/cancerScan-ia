import 'dart:convert';
import 'dart:math';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Stockage de la clé de chiffrement locale.
abstract class KeyStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

/// Keystore Android / Keychain iOS (chiffrement matériel par défaut depuis flutter_secure_storage 10).
class SecureKeyStore implements KeyStore {
  static const _storage = FlutterSecureStorage();
  @override
  Future<String?> read(String key) => _storage.read(key: key);
  @override
  Future<void> write(String key, String value) => _storage.write(key: key, value: value);
  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

/// Pour les tests.
class MemoryKeyStore implements KeyStore {
  final Map<String, String> _values = {};
  @override
  Future<String?> read(String key) async => _values[key];
  @override
  Future<void> write(String key, String value) async => _values[key] = value;
  @override
  Future<void> delete(String key) async => _values.remove(key);
}

/// Chiffrement AES-256-GCM des données de patientes stockées sur l'appareil (cahier des charges §10.4, §11.1).
class Vault {
  Vault._(this._key);

  static const _keyName = 'cancerscan.local_data_key';
  static final _algo = AesGcm.with256bits();
  final SecretKey _key;

  static Future<Vault> open(KeyStore store) async {
    var encoded = await store.read(_keyName);
    if (encoded == null) {
      final rnd = Random.secure();
      encoded = base64Encode(List<int>.generate(32, (_) => rnd.nextInt(256)));
      await store.write(_keyName, encoded);
    }
    return Vault._(SecretKey(base64Decode(encoded)));
  }

  /// Efface la clé : les données locales deviennent illisibles (déconnexion définitive / appareil perdu).
  static Future<void> destroyKey(KeyStore store) => store.delete(_keyName);

  Future<String> encrypt(Map<String, Object?> value) async {
    final box = await _algo.encrypt(utf8.encode(jsonEncode(value)), secretKey: _key);
    return base64Encode(box.concatenation());
  }

  Future<Map<String, dynamic>> decrypt(String token) async {
    final box = SecretBox.fromConcatenation(base64Decode(token),
        nonceLength: _algo.nonceLength, macLength: _algo.macAlgorithm.macLength);
    return jsonDecode(utf8.decode(await _algo.decrypt(box, secretKey: _key))) as Map<String, dynamic>;
  }
}
