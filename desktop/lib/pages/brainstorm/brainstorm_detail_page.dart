import 'package:flutter/material.dart';

class BrainstormDetailPage extends StatelessWidget {
  final String id;
  const BrainstormDetailPage({super.key, required this.id});


  @override
  Widget build(BuildContext context) {
    return Center(child: Text('脑暴详情 $id', style: TextStyle(color: Color(0xFF9CA3AF))));
  }
}
