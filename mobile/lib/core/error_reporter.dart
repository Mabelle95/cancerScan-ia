import 'api_client.dart';
import 'local_store.dart';

/// Erreurs de l'application : mises en file sur l'appareil (souvent hors ligne), envoyées à /client-errors
/// lors de la synchronisation suivante. Aucune donnée de patiente : message et pile tronqués uniquement.
class ErrorReporter {
  ErrorReporter(this.api, this.store, {this.appVersion = '0.1.0'});

  final ApiClient api;
  final LocalStore store;
  final String appVersion;
  static const _key = 'error_queue';
  static const maxQueued = 50;
  final Map<String, DateTime> _recent = {};

  Future<void> report(Object error, StackTrace? stack, {String? screen}) async {
    try {
      final message = '${error.runtimeType}: $error';
      final now = DateTime.now();
      // Même erreur répétée en boucle (ex. pendant un rendu) : un seul rapport par minute
      if (_recent[message]?.isAfter(now.subtract(const Duration(minutes: 1))) ?? false) return;
      _recent[message] = now;
      final queue = List<dynamic>.from(await store.getJson(_key) as List? ?? []);
      queue.add({
        'source': 'mobile',
        'message': message.length > 1000 ? message.substring(0, 1000) : message,
        'stack': stack == null ? null : (stack.toString().length > 4000 ? stack.toString().substring(0, 4000) : stack.toString()),
        'app_version': appVersion,
        'platform': 'android',
        'screen': screen,
        'time': now.toIso8601String(),
      });
      await store.putJson(_key, queue.length > maxQueued ? queue.sublist(queue.length - maxQueued) : queue);
    } catch (_) {/* la remontée d'erreur ne doit jamais provoquer d'autre erreur */}
  }

  Future<int> pending() async => (await store.getJson(_key) as List? ?? []).length;

  /// Envoie la file ; s'arrête au premier échec réseau (les rapports restants partiront plus tard).
  Future<int> flush() async {
    final queue = List<dynamic>.from(await store.getJson(_key) as List? ?? []);
    var sent = 0;
    for (final item in queue) {
      try {
        final body = Map<String, Object?>.from(item as Map)..remove('time');
        await api.reportError(body);
        sent++;
      } on OfflineException {
        break;
      } on ApiException catch (e) {
        if (e.status == 429) break; // limite atteinte : on réessaiera
        sent++; // rapport refusé (ex. invalide) : inutile de le renvoyer
      }
    }
    await store.putJson(_key, queue.sublist(sent));
    return sent;
  }
}
