import 'package:flutter/material.dart';

class StudyDetailPage extends StatelessWidget {
  final String id;
  const StudyDetailPage({super.key, required this.id});


  @override
  Widget build(BuildContext context) {
    return Center(child: Text('辅导详情 $id', style: TextStyle(color: Color(0xFF9CA3AF))));
  }
}
