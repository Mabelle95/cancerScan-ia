import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api_client.dart';
import '../core/app_state.dart';
import '../core/local_store.dart';
import '../theme.dart';
import '../widgets/ui.dart';
import 'dashboard_screen.dart';
import 'login_screen.dart';
import 'result_screen.dart';
import 'screenings_screen.dart';
import 'wizard_screen.dart';

const _roleLabels = {
  'agent_sante': 'Agent de santé',
  'medecin': 'Médecin',
  'specialiste': 'Spécialiste',
  'responsable_sanitaire': 'Responsable sanitaire',
  'admin': 'Administrateur',
};

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<LocalRecord> _screenings = [];

  @override
  void initState() {
    super.initState();
    _load();
    context.read<AppState>().addListener(_load);
  }

  @override
  void dispose() {
    context.read<AppState>().removeListener(_load);
    super.dispose();
  }

  Future<void> _load() async {
    final s = await context.read<AppState>().store.screenings();
    if (mounted) setState(() => _screenings = s);
  }

  Future<void> _logout() async {
    final app = context.read<AppState>();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: const Icon(Icons.logout_rounded),
        title: const Text('Se déconnecter ?'),
        content: const Text('Les données des patientes seront effacées de ce téléphone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), style: FilledButton.styleFrom(minimumSize: const Size(120, 44)), child: const Text('Se déconnecter')),
        ],
      ),
    );
    if (ok != true) return;
    if (!await app.logout() && mounted) {
      showError(context, '${app.pendingCount} dépistage(s) pas encore envoyé(s) : synchronisez avant de vous déconnecter.');
    }
  }

  Future<void> _sync() async {
    final app = context.read<AppState>();
    try {
      final r = await app.syncNow();
      if (mounted && r != null) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(r.hasErrors ? 'Synchronisation partielle : ${r.messages.first}' : 'Synchronisation terminée')));
      }
    } on OfflineException {
      if (mounted) showError(context, 'Pas de connexion : les dépistages restent sur le téléphone et partiront plus tard.');
    } on ApiException catch (e) {
      if (!mounted) return;
      e.isUnauthorized ? _relogin() : showError(context, e);
    }
  }

  void _relogin() => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const LoginScreen(relogin: true)));

  void _open(Widget screen) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));

  String _greeting() {
    final h = DateTime.now().hour;
    return h < 12 ? 'Bonjour' : (h < 18 ? 'Bon après-midi' : 'Bonsoir');
  }

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final name = '${app.user?['full_name'] ?? ''}';
    final initial = name.trim().isEmpty ? '?' : name.trim()[0].toUpperCase();
    final now = DateTime.now();
    final today = _screenings.where((s) => s.createdAt.year == now.year && s.createdAt.month == now.month && s.createdAt.day == now.day).length;
    final weekAgo = now.subtract(const Duration(days: 7));
    final alerts = _screenings.where((s) => s.alertCount > 0 && s.createdAt.isAfter(weekAgo)).length;
    final canScreen = app.can('screenings:write') && app.forms.containsKey('sein');
    final others = app.orderedForms.where((f) => f.pathology != 'sein').toList();

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _sync,
        edgeOffset: 120,
        child: ListView(padding: EdgeInsets.zero, children: [
          // --- En-tête en dégradé ---------------------------------------------------
          Container(
            decoration: const BoxDecoration(
              gradient: AppColors.brandGradient,
              borderRadius: BorderRadius.vertical(bottom: Radius.circular(32)),
            ),
            padding: EdgeInsets.fromLTRB(22, MediaQuery.of(context).padding.top + 14, 12, 74),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                const Icon(Icons.medical_services_rounded, color: Colors.white, size: 22),
                const SizedBox(width: 8),
                const Text('CancerScan', style: TextStyle(color: Colors.white, fontSize: 19, fontWeight: FontWeight.w700, letterSpacing: 0.3)),
                const Spacer(),
                IconButton(tooltip: 'Se déconnecter', onPressed: _logout, icon: const Icon(Icons.logout_rounded, color: Colors.white)),
              ]),
              const SizedBox(height: 18),
              Row(children: [
                Container(
                  padding: const EdgeInsets.all(3),
                  decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: Colors.white54, width: 2)),
                  child: CircleAvatar(
                    radius: 30,
                    backgroundColor: Colors.white,
                    child: Text(initial, style: const TextStyle(color: AppColors.primaryDark, fontSize: 26, fontWeight: FontWeight.w800)),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('${_greeting()},', style: const TextStyle(color: Colors.white70, fontSize: 15)),
                    Text(name, maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(color: Colors.white, fontSize: 23, fontWeight: FontWeight.w800)),
                    Text(_roleLabels[app.user?['role']] ?? '', style: const TextStyle(color: Colors.white70, fontSize: 14)),
                  ]),
                ),
              ]),
              const SizedBox(height: 16),
              _SyncPill(onSync: _sync),
            ]),
          ),

          // --- Chiffres (chevauchent l'en-tête) --------------------------------------
          Transform.translate(
            offset: const Offset(0, -50),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18),
              child: Row(children: [
                Expanded(child: StatTile(value: '$today', label: 'Dépistages\naujourd\'hui', icon: Icons.today_rounded, color: AppColors.primary)),
                const SizedBox(width: 10),
                Expanded(child: StatTile(value: '${app.pendingCount}', label: 'À envoyer\nau serveur', icon: Icons.cloud_upload_rounded, color: AppColors.moyen)),
                const SizedBox(width: 10),
                Expanded(child: StatTile(value: '$alerts', label: 'Avec signes\nd\'alerte (7 j)', icon: Icons.warning_rounded, color: AppColors.eleve)),
              ]),
            ),
          ),

          Transform.translate(
            offset: const Offset(0, -34),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                if (app.needsLogin)
                  Notice(
                    kind: NoticeKind.warning,
                    title: 'Session expirée',
                    text: 'Reconnectez-vous pour envoyer vos dépistages (ils restent sur le téléphone).',
                    action: OutlinedButton(onPressed: _relogin, child: const Text('Se reconnecter')),
                  ),

                // --- Action principale ----------------------------------------------
                if (app.can('screenings:write'))
                  _PrimaryAction(
                    enabled: canScreen,
                    onTap: () => _open(const WizardScreen()),
                    subtitle: canScreen ? 'Cancer du sein · 5 étapes · fonctionne hors ligne' : 'Connectez-vous une fois en ligne pour télécharger les formulaires',
                  ),
                const SizedBox(height: 14),
                Row(children: [
                  Expanded(child: _Tile(icon: Icons.fact_check_rounded, color: AppColors.teal, title: 'Mes dépistages', subtitle: 'Historique et recherche', onTap: () => _open(const ScreeningsScreen()))),
                  const SizedBox(width: 12),
                  Expanded(child: _Tile(icon: Icons.insights_rounded, color: AppColors.violet, title: 'Tableau de bord', subtitle: 'Statistiques', onTap: () => _open(const DashboardScreen()))),
                ]),

                if (app.can('screenings:write') && others.isNotEmpty) ...[
                  const _SectionTitle('Autres dépistages'),
                  Wrap(spacing: 10, runSpacing: 10, children: [
                    for (final f in others)
                      ActionChip(
                        avatar: const Icon(Icons.female_rounded, size: 18, color: AppColors.primary),
                        label: Text(pathologyLabels[f.pathology] ?? f.title, style: const TextStyle(fontWeight: FontWeight.w600)),
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                        onPressed: () => _open(WizardScreen(pathology: f.pathology)),
                      ),
                  ]),
                ],

                // --- Derniers dépistages --------------------------------------------
                if (_screenings.isNotEmpty) ...[
                  Row(children: [
                    const Expanded(child: _SectionTitle('Derniers dépistages')),
                    TextButton(onPressed: () => _open(const ScreeningsScreen()), child: const Text('Tout voir')),
                  ]),
                  for (final s in _screenings.take(3))
                    SoftCard(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      margin: const EdgeInsets.only(bottom: 10),
                      onTap: () => _open(ResultScreen(clientId: s.clientId)),
                      child: Row(children: [
                        CircleAvatar(
                          radius: 22,
                          backgroundColor: riskStyle(s.result?['risk_level'] as String?).$1.withValues(alpha: 0.13),
                          child: Icon(riskStyle(s.result?['risk_level'] as String?).$2, color: riskStyle(s.result?['risk_level'] as String?).$1),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text('${s.payload['patient_label'] ?? 'Patiente'}', maxLines: 1, overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15.5)),
                            const SizedBox(height: 2),
                            Text('${pathologyLabels[s.pathology] ?? ''} · ${formatDate(s.createdAt)}', style: const TextStyle(color: AppColors.muted, fontSize: 13)),
                          ]),
                        ),
                        RiskPill(s.result?['risk_level'] as String?, compact: true),
                      ]),
                    ),
                ],

                // --- À propos ---------------------------------------------------------
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(color: const Color(0xFFE8F1FB), borderRadius: BorderRadius.circular(20)),
                  child: const Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Icon(Icons.info_rounded, color: AppColors.primary),
                    SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'CancerScan estime le risque grâce à l\'intelligence artificielle. C\'est une aide à la décision : '
                        'il ne pose pas de diagnostic. Un signe d\'alerte nécessite toujours une évaluation médicale.',
                        style: TextStyle(fontSize: 14, height: 1.45, color: Color(0xFF29425E)),
                      ),
                    ),
                  ]),
                ),
              ]),
            ),
          ),
        ]),
      ),
    );
  }
}

class _SyncPill extends StatelessWidget {
  const _SyncPill({required this.onSync});
  final VoidCallback onSync;

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final (icon, text) = !app.online
        ? (Icons.cloud_off_rounded, 'Hors ligne — la saisie continue')
        : app.pendingCount > 0
            ? (Icons.cloud_upload_rounded, '${app.pendingCount} dépistage(s) à envoyer')
            : (Icons.cloud_done_rounded, app.lastSync == null ? 'Connecté' : 'À jour · ${formatDate(app.lastSync!)}');
    return Material(
      color: Colors.white.withValues(alpha: 0.16),
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: app.syncing ? null : onSync,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, color: Colors.white, size: 18),
            const SizedBox(width: 8),
            Flexible(child: Text(text, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 13.5))),
            const SizedBox(width: 10),
            app.syncing
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.sync_rounded, color: Colors.white, size: 18),
          ]),
        ),
      ),
    );
  }
}

class _PrimaryAction extends StatelessWidget {
  const _PrimaryAction({required this.enabled, required this.onTap, required this.subtitle});
  final bool enabled;
  final VoidCallback onTap;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: enabled ? 1 : 0.6,
      child: Container(
        decoration: BoxDecoration(
          gradient: AppColors.brandGradient,
          borderRadius: BorderRadius.circular(24),
          boxShadow: const [BoxShadow(color: Color(0x552196F3), blurRadius: 20, offset: Offset(0, 8))],
        ),
        child: Material(
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(24),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: enabled ? onTap : null,
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Row(children: [
                Container(
                  width: 62,
                  height: 62,
                  decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.2), borderRadius: BorderRadius.circular(18)),
                  child: const Icon(Icons.add_rounded, color: Colors.white, size: 38),
                ),
                const SizedBox(width: 18),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('Nouveau dépistage', style: TextStyle(color: Colors.white, fontSize: 21, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 4),
                    Text(subtitle, style: const TextStyle(color: Colors.white70, fontSize: 13.5)),
                  ]),
                ),
                const Icon(Icons.arrow_forward_rounded, color: Colors.white),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile({required this.icon, required this.color, required this.title, required this.subtitle, required this.onTap});
  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SoftCard(
      margin: EdgeInsets.zero,
      padding: const EdgeInsets.all(18),
      onTap: onTap,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          width: 50,
          height: 50,
          decoration: BoxDecoration(gradient: AppColors.gradientOf(color), borderRadius: BorderRadius.circular(15)),
          child: Icon(icon, color: Colors.white, size: 27),
        ),
        const SizedBox(height: 14),
        Text(title, style: const TextStyle(fontSize: 16.5, fontWeight: FontWeight.w800)),
        const SizedBox(height: 2),
        Text(subtitle, style: const TextStyle(color: AppColors.muted, fontSize: 13)),
      ]),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 22, 4, 12),
        child: Text(text, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
      );
}
