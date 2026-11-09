import 'dart:async';
import 'dart:ui';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';

import 'core/api_client.dart';
import 'core/app_state.dart';
import 'core/local_store.dart';
import 'core/vault.dart';
import 'screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final keyStore = SecureKeyStore();
  final vault = await Vault.open(keyStore);
  final store = await LocalStore.open(vault);
  final state = AppState(
    store: store,
    api: ApiClient(baseUrl: defaultApiUrl),
    keyStore: keyStore,
    connectivity: Connectivity().onConnectivityChanged,
  );
  await state.restore();

  // Toute erreur non gérée est mise en file et remontée au serveur à la prochaine synchronisation
  final previous = FlutterError.onError;
  FlutterError.onError = (details) {
    previous?.call(details);
    unawaited(state.errors.report(details.exception, details.stack, screen: details.library));
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    unawaited(state.errors.report(error, stack));
    return true; // l'application continue de fonctionner
  };
  runApp(ChangeNotifierProvider.value(value: state, child: const CancerScanApp()));
}

class CancerScanApp extends StatelessWidget {
  const CancerScanApp({super.key});

  @override
  Widget build(BuildContext context) {
    final loggedIn = context.select<AppState, bool>((s) => s.isLoggedIn);
    return MaterialApp(
      title: 'CancerScan',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      locale: const Locale('fr'),
      supportedLocales: const [Locale('fr')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: loggedIn ? const HomeScreen() : const LoginScreen(),
    );
  }
}
