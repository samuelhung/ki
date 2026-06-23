import 'package:flutter/material.dart';

class EventDetailPage extends StatelessWidget {
  final int id;
  const EventDetailPage({super.key, required this.id});


  @override
  Widget build(BuildContext context) {
    return Center(child: Text('事件详情 #$id', style: TextStyle(color: Color(0xFF9CA3AF))));
  }
}
