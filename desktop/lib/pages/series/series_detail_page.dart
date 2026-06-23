import 'package:flutter/material.dart';

class SeriesDetailPage extends StatelessWidget {
  final int id;
  const SeriesDetailPage({super.key, required this.id});


  @override
  Widget build(BuildContext context) {
    return Center(child: Text('专题详情 #$id', style: TextStyle(color: Color(0xFF9CA3AF))));
  }
}
