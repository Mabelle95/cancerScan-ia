import 'package:flutter/material.dart';

import '../core/local_store.dart';
import '../theme.dart';

const riskLabels = {'faible': 'Risque faible', 'moyen': 'Risque moyen', 'eleve': 'Risque élevé'};
const pathologyLabels = {'sein': 'Sein', 'col': "Col de l'utérus", 'ovaire': 'Ovaire', 'endometre': 'Endomètre'};
const togoRegions = ['Maritime', 'Plateaux', 'Centrale', 'Kara', 'Savanes'];

const _riskColors = {'faible': Color(0xFF43A047), 'moyen': Color(0xFFFB8C00), 'eleve': Color(0xFFE53935)};

/// Niveau de risque : toujours écrit en toutes lettres, jamais signalé par la couleur seule.
class RiskBadge extends StatelessWidget {
  const RiskBadge(this.level, {super.key, this.large = false});
  final String? level;
  final bool large;

  @override
  Widget build(BuildContext context) {
    final color = _riskColors[level] ?? Theme.of(context).colorScheme.outline;
    return Container(
      padding: EdgeInsets.symmetric(horizontal: large ? 16 : 10, vertical: large ? 8 : 3),
      decoration: BoxDecoration(border: Border.all(color: color, width: 1.5), borderRadius: BorderRadius.circular(999)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 9, height: 9, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 6),
        Text(riskLabels[level] ?? 'Non calculé',
            style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: large ? 18 : 13)),
      ]),
    );
  }
}

class AlertChip extends StatelessWidget {
  const AlertChip({super.key, this.text = "Signe d'alerte"});
  final String text;
  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: scheme.errorContainer, borderRadius: BorderRadius.circular(999)),
      child: Text(text, style: TextStyle(color: scheme.onErrorContainer, fontSize: 12, fontWeight: FontWeight.w700)),
    );
  }
}

class SyncStateChip extends StatelessWidget {
  const SyncStateChip(this.state, {super.key});
  final SyncState state;
  @override
  Widget build(BuildContext context) {
    final (text, icon, color) = switch (state) {
      SyncState.pending => ('À synchroniser', Icons.cloud_upload_outlined, const Color(0xFF9A5B00)),
      SyncState.synced => ('Synchronisé', Icons.cloud_done_outlined, const Color(0xFF1D7A46)),
      SyncState.error => ('Erreur', Icons.error_outline, Theme.of(context).colorScheme.error),
    };
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Icon(icon, size: 16, color: color),
      const SizedBox(width: 4),
      Text(text, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600)),
    ]);
  }
}

/// Bandeau d'information (avertissement, alerte, succès).
class Notice extends StatelessWidget {
  const Notice({super.key, required this.text, this.title, this.kind = NoticeKind.info, this.action});
  final String? title;
  final String text;
  final NoticeKind kind;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (bg, fg) = switch (kind) {
      NoticeKind.danger => (scheme.errorContainer, scheme.onErrorContainer),
      NoticeKind.warning => (const Color(0xFFFFF4DC), const Color(0xFF7A4800)),
      NoticeKind.success => (const Color(0xFFE5F5EC), const Color(0xFF145C34)),
      NoticeKind.info => (scheme.surfaceContainerHighest, scheme.onSurface),
    };
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(8)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (title != null) Text(title!, style: TextStyle(color: fg, fontWeight: FontWeight.w700)),
        Text(text, style: TextStyle(color: fg)),
        if (action != null) Padding(padding: const EdgeInsets.only(top: 8), child: action),
      ]),
    );
  }
}

enum NoticeKind { info, warning, danger, success }

String formatDate(DateTime d) =>
    '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year} '
    '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

void showError(BuildContext context, Object e) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e'), backgroundColor: Theme.of(context).colorScheme.error));
}

/// Carte blanche avec icône et titre (« Informations Patient », « Recommandations »…).
class InfoCard extends StatelessWidget {
  const InfoCard({super.key, required this.icon, required this.title, required this.children, this.iconColor});
  final IconData icon;
  final String title;
  final Color? iconColor;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final c = iconColor ?? AppColors.primary;
    return SoftCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(color: c.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
            child: Icon(icon, color: c, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(child: Text(title, style: const TextStyle(fontSize: 17.5, fontWeight: FontWeight.w800))),
        ]),
        const Divider(height: 26),
        ...children,
      ]),
    );
  }
}

class KeyValue extends StatelessWidget {
  const KeyValue(this.label, this.value, {super.key});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: Text(label, style: const TextStyle(color: Colors.black54, fontSize: 15))),
          Flexible(child: Text(value, textAlign: TextAlign.right, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15))),
        ]),
      );
}

/// État de synchronisation, en blanc sur la carte colorée du résultat.
class SyncBadge extends StatelessWidget {
  const SyncBadge(this.state, {super.key});
  final SyncState state;
  @override
  Widget build(BuildContext context) {
    final (text, icon) = switch (state) {
      SyncState.pending => ('Enregistré sur le téléphone — à synchroniser', Icons.cloud_upload_outlined),
      SyncState.synced => ('Synchronisé', Icons.cloud_done_outlined),
      SyncState.error => ('Erreur de synchronisation', Icons.error_outline),
    };
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Icon(icon, color: Colors.white70, size: 16),
      const SizedBox(width: 6),
      Flexible(child: Text(text, style: const TextStyle(color: Colors.white70, fontSize: 13))),
    ]);
  }
}

/// Pastille douce du niveau de risque (texte toujours présent, la couleur n'est jamais seule).
class RiskPill extends StatelessWidget {
  const RiskPill(this.level, {super.key, this.compact = false});
  final String? level;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final (color, icon, label) = riskStyle(level);
    return Container(
      padding: EdgeInsets.symmetric(horizontal: compact ? 8 : 10, vertical: 5),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(999)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 15, color: color),
        const SizedBox(width: 5),
        Text(compact ? shortRiskLabel(level) : label,
            style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 12.5)),
      ]),
    );
  }
}

/// Carte blanche à coins arrondis et ombre douce.
class SoftCard extends StatelessWidget {
  const SoftCard({super.key, required this.child, this.padding = const EdgeInsets.all(20), this.margin = const EdgeInsets.only(bottom: 14), this.onTap});
  final Widget child;
  final EdgeInsets padding;
  final EdgeInsets margin;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: margin,
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(22), boxShadow: softShadow),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(22),
        clipBehavior: Clip.antiAlias,
        child: InkWell(onTap: onTap, child: Padding(padding: padding, child: child)),
      ),
    );
  }
}

/// Petite tuile chiffrée (accueil, tableau de bord).
class StatTile extends StatelessWidget {
  const StatTile({super.key, required this.value, required this.label, required this.icon, required this.color});
  final String value;
  final String label;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 14, 10, 14),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), boxShadow: softShadow),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          padding: const EdgeInsets.all(7),
          decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(10)),
          child: Icon(icon, color: color, size: 20),
        ),
        const SizedBox(height: 10),
        Text(value, style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: color, height: 1)),
        const SizedBox(height: 4),
        Text(label, maxLines: 2, style: const TextStyle(color: AppColors.muted, fontSize: 12.5, height: 1.2)),
      ]),
    );
  }
}

/// Anneau de score animé (0 → score) affiché sur la carte de résultat.
class ScoreRing extends StatelessWidget {
  const ScoreRing({super.key, required this.score, this.size = 150});
  final double score;
  final double size;

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: score.clamp(0, 1)),
      duration: const Duration(milliseconds: 1100),
      curve: Curves.easeOutCubic,
      builder: (context, v, _) => SizedBox(
        width: size,
        height: size,
        child: CustomPaint(
          painter: _RingPainter(v),
          child: Center(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text('${(v * 100).toStringAsFixed(0)} %', style: const TextStyle(color: Colors.white, fontSize: 34, fontWeight: FontWeight.w800)),
              const Text('score estimé', style: TextStyle(color: Colors.white70, fontSize: 12.5)),
            ]),
          ),
        ),
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter(this.value);
  final double value;

  @override
  void paint(Canvas canvas, Size size) {
    final stroke = size.width * 0.085;
    final rect = Rect.fromLTWH(stroke / 2, stroke / 2, size.width - stroke, size.height - stroke);
    final track = Paint()
      ..color = Colors.white24
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke;
    final arc = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = stroke;
    canvas.drawArc(rect, 0, 6.2832, false, track);
    canvas.drawArc(rect, -1.5708, 6.2832 * value, false, arc);
  }

  @override
  bool shouldRepaint(_RingPainter old) => old.value != value;
}

/// Graphique en anneau (répartition des niveaux de risque).
class DonutChart extends StatelessWidget {
  const DonutChart({super.key, required this.segments, this.size = 150, this.centerLabel});
  final List<(double, Color)> segments;
  final double size;
  final Widget? centerLabel;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: size,
        height: size,
        child: CustomPaint(painter: _DonutPainter(segments), child: Center(child: centerLabel)),
      );
}

class _DonutPainter extends CustomPainter {
  _DonutPainter(this.segments);
  final List<(double, Color)> segments;

  @override
  void paint(Canvas canvas, Size size) {
    final stroke = size.width * 0.16;
    final rect = Rect.fromLTWH(stroke / 2, stroke / 2, size.width - stroke, size.height - stroke);
    final total = segments.fold<double>(0, (a, s) => a + s.$1);
    if (total == 0) {
      canvas.drawArc(rect, 0, 6.2832, false, Paint()
        ..color = const Color(0xFFE6ECF2)
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke);
      return;
    }
    var start = -1.5708;
    for (final (v, c) in segments) {
      if (v <= 0) continue;
      final sweep = 6.2832 * v / total;
      canvas.drawArc(rect, start, sweep - 0.03, false, Paint()
        ..color = c
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke);
      start += sweep;
    }
  }

  @override
  bool shouldRepaint(_DonutPainter old) => true;
}
