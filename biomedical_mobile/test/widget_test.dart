import 'package:flutter_test/flutter_test.dart';
import 'package:biomedical_mobile/main.dart';

void main() {
  testWidgets('Smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const BiomedicalApp());
    expect(find.text('ELITE BIOMEDICAL'), findsOneWidget);
  });
}
