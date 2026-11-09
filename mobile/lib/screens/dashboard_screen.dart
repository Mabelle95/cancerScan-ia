import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/app_state.dart';
import '../core/local_store.dart';
import '../theme.dart';
import '../widgets/ui.dart';

/// Tableau de bord de l'agent : activité enregistrée sur ce téléphone (fonctionne hors ligne).
/// Les statistiques nationales agrégées sont sur la plateforme Web (responsables sanitaires).
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});
  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  List<LocalRecord>? _screenings;
  int _patients = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final store = context.read<AppState>().store;
    final s = await store.screenings();
    final p = await store.patients();
    if (mounted) {
      setState(() {
        _screenings = s;
        _patients = p.length;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = _screenings;
    if (s == null) return Scaffold(appBar: AppBar(title: const Text('Tableau de bord')), body: const Center(child: CircularProgressIndicator()));

    final counts = <String?, int>{'eleve': 0, 'moyen': 0, 'faible': 0, null: 0};
    for (final r in s) {
      final level = r.result?['risk_level'] as String?;
      final key = counts.containsKey(level) ? level : null;
      counts[key] = counts[key]! + 1;
    }
    final alerts = s.where((r) => r.alertCount > 0).length;
    final pending = s.where((r) => r.state != SyncState.synced).length;
    final levels = <String?>['eleve', 'moyen', 'faible', null];

    // Activité des 7 derniers jours
    final now = DateTime.now();
    final days = [for (var i = 6; i >= 0; i--) DateTime(now.year, now.month, now.day).subtract(Duration(days: i))];
    final perDay = [for (final d in days) s.where((r) => r.createdAt.year == d.year && r.createdAt.month == d.month && r.createdAt.day == d.day).length];
    final maxDay = perDay.fold<int>(1, (a, b) => b > a ? b : a);
    const weekdays = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];

    return Scaffold(
      appBar: AppBar(title: const Text('Tableau de bord')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(padding: const EdgeInsets.fromLTRB(16, 18, 16, 28), children: [
          const Padding(
            padding: EdgeInsets.only(left: 4, bottom: 12),
            child: Text('Activité enregistrée sur ce téléphone', style: TextStyle(color: AppColors.muted, fontWeight: FontWeight.w600)),
          ),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 12,
            crossAxisSpacing: 12,
            childAspectRatio: 1.35,
            children: [
              StatTile(value: '${s.length}', label: 'Dépistages', icon: Icons.assignment_rounded, color: AppColors.primary),
              StatTile(value: '$_patients', label: 'Nouvelles patientes', icon: Icons.person_add_alt_1_rounded, color: AppColors.teal),
              StatTile(value: '$alerts', label: 'Avec signes d\'alerte', icon: Icons.warning_rounded, color: AppColors.eleve),
              StatTile(value: '$pending', label: 'À synchroniser', icon: Icons.cloud_upload_rounded, color: AppColors.moyen),
            ],
          ),
          const SizedBox(height: 16),

          // --- Répartition des risques -------------------------------------------------
          InfoCard(icon: Icons.donut_large_rounded, title: 'Répartition des risques estimés', children: [
            Row(children: [
              DonutChart(
                size: 140,
                segments: [for (final l in levels) (counts[l]!.toDouble(), riskStyle(l).$1)],
                centerLabel: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text('${s.length}', style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800)),
                  const Text('au total', style: TextStyle(color: AppColors.muted, fontSize: 12)),
                ]),
              ),
              const SizedBox(width: 20),
              Expanded(
                child: Column(children: [
                  for (final l in levels)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: Row(children: [
                        Container(width: 12, height: 12, decoration: BoxDecoration(color: riskStyle(l).$1, borderRadius: BorderRadius.circular(4))),
                        const SizedBox(width: 10),
                        Expanded(child: Text(shortRiskLabel(l), style: const TextStyle(fontSize: 14.5))),
                        Text('${counts[l]}', style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                      ]),
                    ),
                ]),
              ),
            ]),
          ]),

          // --- 7 derniers jours ------------------------------------------------------------
          InfoCard(icon: Icons.bar_chart_rounded, iconColor: AppColors.violet, title: '7 derniers jours', children: [
            SizedBox(
              height: 150,
              child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                for (var i = 0; i < 7; i++)
                  Expanded(
                    child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                      Text('${perDay[i]}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12.5)),
                      const SizedBox(height: 4),
                      TweenAnimationBuilder<double>(
                        tween: Tween(begin: 0, end: perDay[i] / maxDay),
                        duration: const Duration(milliseconds: 700),
                        curve: Curves.easeOutCubic,
                        builder: (context, v, _) => Container(
                          height: 4 + 96 * v,
                          margin: const EdgeInsets.symmetric(horizontal: 7),
                          decoration: BoxDecoration(
                            gradient: i == 6 ? AppColors.brandGradient : AppColors.gradientOf(AppColors.primaryLight),
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(weekdays[days[i].weekday - 1],
                          style: TextStyle(color: i == 6 ? AppColors.primary : AppColors.muted, fontWeight: i == 6 ? FontWeight.w800 : FontWeight.w500)),
                    ]),
                  ),
              ]),
            ),
          ]),

          const Notice(text: 'Les données synchronisées depuis plus de 30 jours sont effacées du téléphone (limitation de la conservation). '
              'Les statistiques complètes sont sur la plateforme Web.'),
        ]),
      ),
    );
  }
}
