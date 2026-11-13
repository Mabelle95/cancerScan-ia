import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../theme.dart';
import 'ui.dart';

/// Structures spécialisées les plus proches de la patiente, proposées par le serveur pour un risque
/// moyen ou élevé. La première est la plus proche ; l'agent peut appeler ou ouvrir l'itinéraire.
class ReferralPlacesCard extends StatelessWidget {
  const ReferralPlacesCard({super.key, required this.level, required this.places, this.chosenId, this.decided = false});
  final String? level;
  /// Le médecin a pris sa décision : seule la structure retenue est affichée (aucune s'il ne réfère pas)
  final bool decided;
  final List<Map<String, dynamic>> places;
  /// Structure retenue par le médecin (si la décision est déjà prise)
  final int? chosenId;

  @override
  Widget build(BuildContext context) {
    final (color, _, _) = riskStyle(level);
    final shown = decided ? places.where((p) => p['facility_id'] == chosenId).toList() : places;
    if (shown.isEmpty) return const SizedBox.shrink();
    final urgent = level == 'eleve' && !decided;
    return InfoCard(
      icon: Icons.near_me_rounded,
      iconColor: color,
      title: decided ? 'Structure de référence' : urgent ? 'Orienter la patiente au plus vite' : 'Où orienter la patiente',
      children: [
        if (!decided) Text(
          urgent
              ? 'Structures spécialisées les plus proches. Aidez la patiente à prendre rendez-vous rapidement.'
              : 'Structures spécialisées les plus proches pour une consultation.',
          style: const TextStyle(color: Colors.black54, fontSize: 14),
        ),
        const SizedBox(height: 12),
        for (final (i, p) in shown.indexed) _Place(place: p, highlight: chosenId == null ? i == 0 : chosenId == p['facility_id'], color: color, chosen: chosenId == p['facility_id']),
        const SizedBox(height: 4),
        const Text('Distances à vol d\'oiseau depuis votre centre : le trajet par la route est plus long.',
            style: TextStyle(fontSize: 12, color: Colors.black54)),
      ],
    );
  }
}

class _Place extends StatelessWidget {
  const _Place({required this.place, required this.highlight, required this.color, required this.chosen});
  final Map<String, dynamic> place;
  final bool highlight;
  final bool chosen;
  final Color color;

  Future<void> _open(BuildContext context, Uri uri) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      if (await launchUrl(uri, mode: LaunchMode.externalApplication)) return;
    } catch (_) {}
    messenger.showSnackBar(const SnackBar(content: Text('Impossible d\'ouvrir cette action sur ce téléphone.')));
  }

  @override
  Widget build(BuildContext context) {
    final km = place['distance_km'] as num?;
    final phone = place['phone'] as String?;
    final lat = place['latitude'] as num?, lon = place['longitude'] as num?;
    final where = [place['district'], place['region']].whereType<String>().join(', ');
    // Libellés envoyés par le serveur (clé brute pour un résultat enregistré avant leur ajout)
    final services = [for (final s in (place['service_labels'] ?? place['services']) as List? ?? []) '$s'];
    final distance = place['same_facility'] == true
        ? 'Dans votre centre'
        : km == null
            ? 'Distance inconnue'
            : km < 1
                ? 'Moins de 1 km'
                : '${km.toStringAsFixed(km < 10 ? 1 : 0)} km';

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: highlight ? color.withValues(alpha: 0.08) : Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: highlight ? color.withValues(alpha: 0.5) : Colors.black12, width: highlight ? 1.6 : 1),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (chosen || highlight)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(chosen ? 'RETENUE PAR LE MÉDECIN' : 'LA PLUS PROCHE',
                      style: TextStyle(color: color, fontSize: 11.5, fontWeight: FontWeight.w800, letterSpacing: 0.5)),
                ),
              Text('${place['name']}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              if (where.isNotEmpty) Text(where, style: const TextStyle(color: Colors.black54, fontSize: 13.5)),
              if (place['address'] != null) Text('${place['address']}', style: const TextStyle(color: Colors.black54, fontSize: 13.5)),
            ]),
          ),
          const SizedBox(width: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(color: AppColors.primary.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(20)),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.place_rounded, size: 16, color: AppColors.primaryDark),
              const SizedBox(width: 3),
              Text(distance, style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.primaryDark, fontSize: 13)),
            ]),
          ),
        ]),
        if (services.isNotEmpty) ...[
          const SizedBox(height: 10),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final s in services)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(color: AppColors.background, borderRadius: BorderRadius.circular(8)),
                child: Text(s, style: const TextStyle(fontSize: 12.5)),
              ),
          ]),
        ],
        if (phone != null || (lat != null && lon != null)) ...[
          const SizedBox(height: 12),
          Row(children: [
            if (phone != null)
              Expanded(
                child: FilledButton.icon(
                  onPressed: () => _open(context, Uri(scheme: 'tel', path: phone.replaceAll(' ', ''))),
                  icon: const Icon(Icons.call_rounded, size: 20),
                  label: const Text('Appeler'),
                ),
              ),
            if (phone != null && lat != null && lon != null) const SizedBox(width: 10),
            if (lat != null && lon != null)
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => _open(context, Uri.parse('https://www.google.com/maps/dir/?api=1&destination=$lat,$lon')),
                  icon: const Icon(Icons.directions_rounded, size: 20),
                  label: const Text('Itinéraire'),
                ),
              ),
          ]),
        ],
      ]),
    );
  }
}
