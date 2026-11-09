import 'dart:convert';
import 'dart:io';

import 'package:cancerscan/core/form_logic.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  // Le vrai formulaire partagé : le test échoue si le formulaire évolue de façon incompatible.
  final sein = FormDef.fromJson(jsonDecode(File('../shared/forms/sein.json').readAsStringSync()) as Map<String, dynamic>);
  final complet = <String, Object?>{
    'atcd_familial_sein_ovaire': false,
    'atcd_personnel_sein': false,
    'masse_presente': false,
    'modif_peau': false,
    'retraction_mamelon': 'inconnu',
    'examen_realise': true,
    'probabilite_enqueteur': 'faible',
  };

  test('champs conditionnels', () {
    expect(isVisible(sein.field('masse_taille_cm')!, {'masse_presente': true}), isTrue);
    expect(isVisible(sein.field('masse_taille_cm')!, {'masse_presente': false}), isFalse);
    expect(isVisible(sein.field('age_premiere_grossesse')!, {'nb_grossesses_terme': 0}), isFalse);
    expect(isVisible(sein.field('age_premiere_grossesse')!, {'nb_grossesses_terme': 2}), isTrue);
  });

  test('obligatoires : « inconnu » compte comme une réponse', () {
    expect(checkForm(sein, {}).missing, contains('masse_presente'));
    expect(checkForm(sein, complet).isComplete, isTrue);
  });

  test('bornes et types', () {
    final r = checkForm(sein, {...complet, 'age_premieres_regles': 3, 'nb_grossesses_terme': 2.5});
    expect(r.errors['age_premieres_regles'], startsWith('Minimum'));
    expect(r.errors['nb_grossesses_terme'], 'Nombre entier attendu');
  });

  test("signes d'alerte détectés hors ligne", () {
    final r = checkForm(sein, {...complet, 'retraction_mamelon': true, 'ecoulement': 'sanglant'});
    expect(r.alerts.map((f) => f.id).toSet(), {'retraction_mamelon', 'ecoulement'});
  });

  test("les champs masqués ne sont pas envoyés", () {
    final r = checkForm(sein, {...complet, 'nb_grossesses_terme': 0, 'age_premiere_grossesse': 25});
    expect(r.cleaned.containsKey('age_premiere_grossesse'), isFalse);
  });

  test('affichage : inconnu, non et absent sont distincts', () {
    final f = sein.field('modif_peau')!;
    expect(displayValue(f, false), 'Non');
    expect(displayValue(f, 'inconnu'), 'Inconnu');
    expect(displayValue(f, null), '—');
  });
}
