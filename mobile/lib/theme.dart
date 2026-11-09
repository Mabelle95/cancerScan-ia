import 'package:flutter/material.dart';

/// Charte CancerScan : bleu, dégradés doux, cartes arrondies, gros boutons faciles à toucher.
class AppColors {
  static const primary = Color(0xFF2196F3);
  static const primaryDark = Color(0xFF1565C0);
  static const primaryLight = Color(0xFF64B5F6);
  static const background = Color(0xFFF3F6FA);
  static const ink = Color(0xFF1B2533);
  static const muted = Color(0xFF6B7785);
  static const faible = Color(0xFF2E9E5B);
  static const moyen = Color(0xFFF59E0B);
  static const eleve = Color(0xFFE53935);
  static const pending = Color(0xFF78909C);
  static const alert = Color(0xFFC62828);
  static const teal = Color(0xFF0E9F8E);
  static const violet = Color(0xFF8E44AD);

  static const brandGradient = LinearGradient(
    colors: [Color(0xFF1565C0), Color(0xFF2196F3), Color(0xFF42A5F5)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  /// Dégradé d'une couleur vers sa version plus sombre (cartes de résultat, tuiles).
  static LinearGradient gradientOf(Color c) => LinearGradient(
        colors: [Color.lerp(c, Colors.white, 0.08)!, Color.lerp(c, Colors.black, 0.22)!],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      );
}

/// Ombre douce commune aux cartes.
const softShadow = [BoxShadow(color: Color(0x1A1B2533), blurRadius: 18, offset: Offset(0, 6))];

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: AppColors.primary, primary: AppColors.primary, surface: Colors.white);
  final rounded = RoundedRectangleBorder(borderRadius: BorderRadius.circular(14));
  final base = ThemeData(useMaterial3: true, colorScheme: scheme);
  return base.copyWith(
    scaffoldBackgroundColor: AppColors.background,
    textTheme: base.textTheme.apply(bodyColor: AppColors.ink, displayColor: AppColors.ink),
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.primary,
      foregroundColor: Colors.white,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(color: Colors.white, fontSize: 21, fontWeight: FontWeight.w600, letterSpacing: 0.2),
    ),
    cardTheme: CardThemeData(
      color: Colors.white,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 14),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20), side: const BorderSide(color: Color(0xFFE6ECF2))),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: const Color(0xFFF8FAFC),
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Color(0xFFD5DEE8))),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: AppColors.primary, width: 2)),
      labelStyle: const TextStyle(color: AppColors.muted),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.primary,
        minimumSize: const Size.fromHeight(56),
        shape: rounded,
        elevation: 0,
        textStyle: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700, letterSpacing: 0.2),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(56),
        shape: rounded,
        side: const BorderSide(color: Color(0xFFC9D6E3), width: 1.5),
        foregroundColor: AppColors.primaryDark,
        textStyle: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      side: const BorderSide(color: Color(0xFFD5DEE8)),
      backgroundColor: Colors.white,
    ),
    snackBarTheme: SnackBarThemeData(behavior: SnackBarBehavior.floating, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
    dividerTheme: const DividerThemeData(color: Color(0xFFE6ECF2)),
  );
}

/// Couleur, icône et libellé d'un niveau de risque (null = analyse pas encore calculée).
(Color, IconData, String) riskStyle(String? level) => switch (level) {
      'faible' => (AppColors.faible, Icons.check_circle_rounded, 'Risque faible'),
      'moyen' => (AppColors.moyen, Icons.warning_rounded, 'Risque moyen'),
      'eleve' => (AppColors.eleve, Icons.priority_high_rounded, 'Risque élevé'),
      _ => (AppColors.pending, Icons.hourglass_top_rounded, 'Analyse en attente'),
    };

IconData sectionIcon(String? key) => switch (key) {
      'person' => Icons.person_rounded,
      'symptoms' => Icons.healing_rounded,
      'exam' => Icons.medical_services_rounded,
      'document' => Icons.note_add_rounded,
      'check' => Icons.task_alt_rounded,
      _ => Icons.assignment_rounded,
    };

/// Libellé court d'une étape de l'assistant.
String stepLabel(String sectionId, int index) => switch (sectionId) {
      'antecedents' => 'Identité',
      'symptomes' => 'Symptômes',
      'examen_clinique' => 'Examen',
      'donnees_complementaires' => 'Infos',
      'orientation' => 'Validation',
      'facteurs_risque' => 'Risques',
      _ => 'Étape ${index + 1}',
    };

/// Libellé court d'un niveau : « Élevé », « Moyen », « Faible », « En attente ».
String shortRiskLabel(String? level) => switch (level) {
      'faible' => 'Faible',
      'moyen' => 'Moyen',
      'eleve' => 'Élevé',
      _ => 'En attente',
    };
