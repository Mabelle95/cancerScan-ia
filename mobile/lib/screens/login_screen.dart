import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api_client.dart';
import '../core/app_state.dart';
import '../theme.dart';
import '../widgets/ui.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, this.relogin = false});
  /// Session expirée : même compte, les saisies locales sont conservées.
  final bool relogin;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _server = TextEditingController();
  bool _busy = false;
  bool _showPassword = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final app = context.read<AppState>();
    _server.text = app.api.baseUrl;
    if (widget.relogin) _email.text = app.user?['email'] as String? ?? '';
  }

  Future<void> _submit() async {
    // Vérification locale en français (sinon le serveur répond par un message de validation technique)
    final email = _email.text.trim();
    if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email) || _password.text.isEmpty) {
      setState(() => _error = 'Saisissez votre identifiant (adresse e-mail) et votre mot de passe.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final app = context.read<AppState>();
    try {
      await app.setServerUrl(_server.text);
      await app.login(email, _password.text);
      if (mounted && widget.relogin) Navigator.of(context).pop();
    } on OfflineException {
      setState(() => _error = 'Serveur injoignable. La première connexion nécessite Internet ; ensuite l\'application fonctionne hors ligne.');
    } on ApiException catch (e) {
      setState(() => _error = e.status == 401 ? 'Identifiant ou mot de passe incorrect.' : e.message);
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _serverSettings() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Adresse du serveur'),
        content: TextField(controller: _server, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'URL de l\'API')),
        actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('OK'))],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: widget.relogin ? AppBar(title: const Text('Session expirée')) : null,
      body: Container(
        decoration: const BoxDecoration(gradient: AppColors.brandGradient),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 440),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  // --- Logo -------------------------------------------------------------
                  Center(
                    child: Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(shape: BoxShape.circle, color: Colors.white.withValues(alpha: 0.18)),
                      child: Container(
                        width: 112,
                        height: 112,
                        decoration: const BoxDecoration(
                          shape: BoxShape.circle,
                          color: Colors.white,
                          boxShadow: [BoxShadow(color: Color(0x40000000), blurRadius: 24, offset: Offset(0, 10))],
                        ),
                        child: const Icon(Icons.medical_services_rounded, color: AppColors.primary, size: 56),
                      ),
                    ),
                  ),
                  const SizedBox(height: 22),
                  const Text('CancerScan', textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.white, fontSize: 34, fontWeight: FontWeight.w800, letterSpacing: 0.5)),
                  const SizedBox(height: 6),
                  const Text('Dépistage du Cancer du Sein', textAlign: TextAlign.center, style: TextStyle(color: Colors.white70, fontSize: 16.5)),
                  const SizedBox(height: 32),

                  // --- Formulaire -------------------------------------------------------
                  Container(
                    padding: const EdgeInsets.fromLTRB(22, 26, 22, 18),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(28),
                      boxShadow: const [BoxShadow(color: Color(0x33000000), blurRadius: 30, offset: Offset(0, 12))],
                    ),
                    child: AutofillGroup(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                        Text(widget.relogin ? 'Reconnectez-vous' : 'Connexion',
                            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
                        const SizedBox(height: 4),
                        Text(widget.relogin ? 'Vos dépistages sont conservés sur le téléphone.' : 'Accès réservé aux professionnels de santé',
                            style: const TextStyle(color: AppColors.muted)),
                        const SizedBox(height: 20),
                        if (_error != null) Notice(kind: NoticeKind.danger, text: _error!),
                        TextField(
                          controller: _email,
                          keyboardType: TextInputType.emailAddress,
                          autofillHints: const [AutofillHints.username],
                          decoration: const InputDecoration(prefixIcon: Icon(Icons.person_rounded), hintText: 'Identifiant (adresse e-mail)'),
                        ),
                        const SizedBox(height: 14),
                        TextField(
                          controller: _password,
                          obscureText: !_showPassword,
                          autofillHints: const [AutofillHints.password],
                          onSubmitted: (_) => _submit(),
                          decoration: InputDecoration(
                            prefixIcon: const Icon(Icons.lock_rounded),
                            hintText: 'Mot de passe',
                            suffixIcon: IconButton(
                              tooltip: _showPassword ? 'Masquer' : 'Afficher',
                              icon: Icon(_showPassword ? Icons.visibility_off_rounded : Icons.visibility_rounded),
                              onPressed: () => setState(() => _showPassword = !_showPassword),
                            ),
                          ),
                        ),
                        const SizedBox(height: 22),
                        FilledButton(
                          onPressed: _busy ? null : _submit,
                          child: _busy
                              ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                              : const Text('Se connecter'),
                        ),
                        const SizedBox(height: 10),
                        TextButton(onPressed: _serverSettings, child: const Text('Paramètres du serveur', style: TextStyle(color: AppColors.muted))),
                      ]),
                    ),
                  ),
                  const SizedBox(height: 22),
                  const Text("Pas de compte ? Demandez-le à l'administrateur de votre district.",
                      textAlign: TextAlign.center, style: TextStyle(color: Colors.white, fontSize: 14.5)),
                  const SizedBox(height: 8),
                  const Text("Outil d'aide à la décision : il ne pose pas de diagnostic.",
                      textAlign: TextAlign.center, style: TextStyle(color: Colors.white70, fontSize: 12.5)),
                ]),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
