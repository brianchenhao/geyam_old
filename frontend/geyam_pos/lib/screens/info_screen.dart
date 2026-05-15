import 'package:flutter/material.dart';

import '../config/theme.dart';
import '../widgets/sakura_overlay.dart';

/// Project info page — abstract, problem statement, objectives.
class InfoScreen extends StatelessWidget {
  const InfoScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1428),
      body: Stack(children: [
        const Positioned.fill(child: SakuraOverlay()),
        SafeArea(
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                child: Row(
                  children: [
                    IconButton(
                      icon: const Icon(Icons.arrow_back, color: Colors.white),
                      onPressed: () => Navigator.of(context).pop(),
                    ),
                    const SizedBox(width: 8),
                    const Text('GEYAM',
                      style: TextStyle(color: Colors.white, fontSize: 18,
                        fontWeight: FontWeight.w700, letterSpacing: 2),
                    ),
                    const Spacer(),
                    const Text('Info',
                      style: TextStyle(color: Colors.white70, fontSize: 14, letterSpacing: 1)),
                  ],
                ),
              ),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 860),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('About the project',
                            style: TextStyle(color: GeyamTheme.accent, fontSize: 12,
                              letterSpacing: 1.5, fontWeight: FontWeight.w600),
                          ),
                          const SizedBox(height: 12),
                          const Text('Project Info',
                            style: TextStyle(color: Colors.white, fontSize: 36,
                              fontWeight: FontWeight.w700, height: 1.15),
                          ),
                          const SizedBox(height: 32),
                          _section('Abstract',
                            'The fast progress in artificial intelligence (AI) and machine learning (ML) has changed the food service industry, especially point of sale (POS) systems (Kasem, Hamada, and Taj-Eddin, 2023). Traditional POS systems have problems like manual data entry errors, high costs, and limited analytical abilities. This project suggests an AI sales system that uses image recognition to automate food tracking, and ML algorithms for predicting sales. This provides an affordable and useful option to current systems. The system tries to fix key problems faced by food service businesses, like high initial costs and poor stock control. By using smartphones for POS functions and analytics, the solution is a cost-effective and scalable option for small businesses.',
                          ),
                          const SizedBox(height: 24),
                          _section('Problem Statement',
                            'Today\'s sales systems in the food industry rely heavily on manual food selection which could be further improved with todays technology. Sharma et al. (2022) demonstrated that manual data entry in traditional sales systems leads to significant operational loses and human errors. More advanced options are often locked behind expensive paywalls, and purchasing a full touch-screen POS system can cost alot. Thompson et al. (2022) observed that the cost of typical point-of-sale systems is a big challenge for small food service places. They noted that entering data by hand causes mistakes in tracking, which hurts the quality of sales data and inventory control. Kumar and Singh (2022) also found that doing things by hand lowers the quality of real-time data, which hurts business choices. High repair costs and subscription fees add to the load on small businesses. Many food sellers can\'t use up-to-date systems because they are not easy to get, and not having AI means they miss chances to predict sales and control stock well. Garcia and Martinez (2023) pointed out that businesses without predictive analytics often overspend on supplies, leading to waste. According to Food Waste Index Report by United Nations Environment Program (2024), food waste is responsible for approximately 8-10% of global greenhouse gas emissions, covering both food loss and food waste stages. Additionally, the production of food that ultimately goes to waste occupies nearly 30% of the world\'s agricultural land.',
                          ),
                          const SizedBox(height: 24),
                          _objectivesSection(),
                          const SizedBox(height: 48),
                          Center(
                            child: Text('© GEYAM 2026 · v2.0',
                              style: TextStyle(color: Colors.white.withValues(alpha: 0.4), fontSize: 12),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ]),
    );
  }

  Widget _section(String title, String body) => Container(
    padding: const EdgeInsets.all(24),
    decoration: BoxDecoration(
      color: const Color(0xFF121E3A),
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title,
          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
        const SizedBox(height: 12),
        Text(body,
          style: TextStyle(color: Colors.white.withValues(alpha: 0.75), fontSize: 14, height: 1.7)),
      ],
    ),
  );

  Widget _objectivesSection() {
    const items = [
      'To study the limitations of traditional sales systems in food service businesses',
      'To develop AI-powered solutions for real-time food identification and data entry to optimize operations.',
      'To integrate AI-Driven analytics for sales forecasting and inventory management',
      'To test and evaluate the system\'s performance in improving efficient sales and inventory management.',
    ];
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF121E3A),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Objectives',
            style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          ...items.map((t) => Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('•  ',
                  style: TextStyle(color: GeyamTheme.accent, fontSize: 14, fontWeight: FontWeight.w700)),
                Expanded(
                  child: Text(t,
                    style: TextStyle(color: Colors.white.withValues(alpha: 0.75), fontSize: 14, height: 1.6)),
                ),
              ],
            ),
          )),
        ],
      ),
    );
  }
}
