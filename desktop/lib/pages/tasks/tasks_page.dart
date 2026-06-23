import 'dart:async';
import 'package:flutter/material.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

const _SRC_L = {'manual':'手工','content':'内容','series':'专题','brainstorm':'脑暴'};
const _SRC_C = {'manual':Color(0xFF6B7280),'content':Color(0xFF10B981),'series':Color(0xFF8B5CF6),'brainstorm':Color(0xFFF59E0B)};
const _PRI_L = {'high':'高','medium':'中','low':'低'};
const _PRI_C = {'high':Color(0xFFF87171),'medium':Color(0xFFFBBF24),'low':Color(0xFF9CA3AF)};
const _ST_L = {'todo':'待处理','in_progress':'进行中','done':'已完成'};
const _ST_O = ['todo','in_progress','done'];
const _WD = ['一','二','三','四','五','六','日'];
// 日历条目轮换色板（每行一色，纯视觉区分）
const _tCal = [Color(0xFF10B981),Color(0xFF8B5CF6),Color(0xFFF59E0B),Color(0xFF38BDF8),Color(0xFFF87171),Color(0xFF34D399)];
Color _tc(int i) => _tCal[i % _tCal.length];

String _fd(DateTime d) => '${d.year}-${d.month.toString().padLeft(2,'0')}-${d.day.toString().padLeft(2,'0')}';
Color _stc(String? s) { switch(s) { case'done':return Color(0xFF10B981); case'in_progress':return Color(0xFFF59E0B); default:return Color(0xFF9CA3AF); } }

class TasksPage extends StatefulWidget { const TasksPage({super.key}); State<TasksPage> createState() => _TasksPageState(); }

class _TasksPageState extends State<TasksPage> {
  final _api = ApiClient();
  List<Map<String,dynamic>> _tasks = [];
  bool _loading = true, _shc = false, _edit = false, _judge = false;
  String? _error;
  String _view = 'list', _search = '', _fs = '', _fp = '', _fst = '';
  Timer? _st;
  late int _y, _mo, _d;
  late DateTime _ws;
  String _sd = '';
  Map<String,dynamic>? _detail;
  final _et = TextEditingController(), _ed = TextEditingController();
  String _ep = 'medium', _edd = '', _es = 'todo';
  final _nt = TextEditingController(), _ndesc = TextEditingController();
  String _np = 'medium', _ndd = '';

  @override void initState() {
    super.initState();
    var n = DateTime.now();
    _y = n.year; _mo = n.month - 1; _d = n.day;
    _ws = _gws(n); _sd = _fd(n);
    _load();
  }
  @override void dispose() { _st?.cancel(); _et.dispose(); _ed.dispose(); _nt.dispose(); _ndesc.dispose(); super.dispose(); }

  DateTime _gws(DateTime d) => d.subtract(Duration(days: d.weekday - 1));
  List<Map<String,dynamic>> _tod(String ds) => _tasks.where((t) => t['due_date'] == ds).toList();

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      List<Map<String,dynamic>> items;
      if (_view == 'list') {
        var r = await _api.getTasks(limit: 200,
          status: _fst.nE, source: _fs.nE, priority: _fp.nE, search: _search.nE);
        items = (r['items'] as List<dynamic>?)?.cast<Map<String,dynamic>>() ?? [];
      } else {
        String from, to;
        if (_view == 'month') {
          from = '$_y-${(_mo+1).toString().padLeft(2,'0')}-01';
          to = '$_y-${(_mo+1).toString().padLeft(2,'0')}-31';
        } else if (_view == 'week') {
          from = _fd(_ws); to = _fd(_ws.add(Duration(days: 6)));
        } else {
          from = to = _fd(DateTime(_y, _mo+1, _d));
        }
        items = (await _api.getTasksDue(from, to)).cast<Map<String,dynamic>>();
      }
      if (mounted) setState(() { _tasks = items; _loading = false; });
    } catch (e) { if (mounted) setState(() { _error = e.toString(); _loading = false; }); }
  }

  void _onSearch(String v) { _search = v; _st?.cancel(); _st = Timer(Duration(milliseconds: 300), _load); }
  void _setView(String v) { setState(() => _view = v); _load(); }

  Future<void> _openDetail(String id) async {
    try {
      setState(() { _detail = null; _edit = false; _judge = false; });
      var d = await _api.getTask(id);
      if (mounted) setState(() => _detail = d);
    } catch (_) {}
  }

  Future<void> _updateStatus(String id, String s) async { await _api.updateTask(id, {'status': s}); _load(); }

  Future<void> _deleteTask(String id) async {
    var ok = await showDialog<bool>(context: context, builder: (c) => AlertDialog(
      backgroundColor: AppTheme.panel,
      title: Text('删除', style: TextStyle(color: AppTheme.textPrimary)),
      content: Text('确定删除？', style: TextStyle(color: AppTheme.textMuted)),
      actions: [
        TextButton(onPressed: () => Navigator.pop(c, false), child: Text('取消')),
        TextButton(onPressed: () => Navigator.pop(c, true), child: Text('删除', style: TextStyle(color: AppTheme.error))),
      ],
    ));
    if (ok != true) return;
    await _api.deleteTask(id);
    _load();
  }

  void _startEdit() {
    if (_detail == null) return;
    _et.text = _detail!['title'] ?? '';
    _ed.text = _detail!['description'] ?? '';
    _ep = _detail!['priority'] ?? 'medium';
    _edd = _detail!['due_date'] ?? '';
    _es = _detail!['status'] ?? 'todo';
    setState(() => _edit = true);
  }

  Future<void> _saveEdit() async {
    if (_detail == null || _et.text.trim().isEmpty) return;
    var u = await _api.updateTask(_detail!['id'], {
      'title': _et.text.trim(), 'description': _ed.text.trim(),
      'priority': _ep, 'due_date': _edd.isEmpty ? null : _edd, 'status': _es,
    });
    setState(() { _detail = u; _edit = false; });
    _load();
  }

  Future<void> _runJudge() async {
    if (_detail == null) return;
    setState(() => _judge = true);
    try {
      await _api.judgeTask(_detail!['id']);
      _detail = await _api.getTask(_detail!['id']);
      if (mounted) setState(() => _judge = false);
    } catch (_) { if (mounted) setState(() => _judge = false); }
  }

  Future<void> _createTask() async {
    var t = _nt.text.trim();
    if (t.isEmpty) return;
    await _api.createTask({
      'title': t, 'description': _ndesc.text.trim(),
      'priority': _np, 'due_date': _ndd.isEmpty ? null : _ndd, 'source': 'manual',
    });
    _closeCreate(); _load();
  }

  void _openCreate({String? dueDate}) {
    _nt.clear(); _ndesc.clear(); _np = 'medium'; _ndd = dueDate ?? '';
    setState(() => _shc = true);
  }
  void _closeCreate() { _nt.clear(); _ndesc.clear(); setState(() => _shc = false); }

  void _navMonth(int d) {
    int m = _mo + d;
    _mo = ((m % 12) + 12) % 12;
    _y += m ~/ 12;
    if (m < 0 && _mo > 0) _y--;
    _load();
  }
  void _navWeek(int d) { _ws = _ws.add(Duration(days: d * 7)); _mo = _ws.month - 1; _y = _ws.year; _load(); }
  void _navDay(int d) {
    var n = DateTime(_y, _mo + 1, _d).add(Duration(days: d));
    _y = n.year; _mo = n.month - 1; _d = n.day;
    _load();
  }

  @override
  Widget build(BuildContext c) => Scaffold(
    backgroundColor: AppTheme.background,
    body: SafeArea(child: Stack(children: [
      Column(children: [
        _buildHeader(), _buildViewToggle(),
        Divider(height: 1, color: AppTheme.border),
        if (_view == 'list') _buildFilters(),
        Expanded(child: _buildContent()),
      ]),
      if (_detail != null) _buildDetailOverlay(),
      if (_shc) _buildCreateOverlay(),
    ])),
  );

  // ── Header ──
  Widget _buildHeader() => Padding(
    padding: EdgeInsets.fromLTRB(32, 24, 32, 8),
    child: Row(children: [
      Icon(Icons.checklist, color: Color(0xFF38BDF8), size: 28),
      SizedBox(width: 12),
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('待办事务', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w700)),
        Text('每一个想法，都值得被认真对待 ✨  ·  v1.0.46', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
      ])),
      _btn('新建', Icons.add, () => _openCreate()),
    ]),
  );

  Widget _btn(String l, IconData i, VoidCallback f) => GestureDetector(
    onTap: f,
    child: Container(
      padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Color(0xFF38BDF8).withOpacity(0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Color(0xFF38BDF8).withOpacity(0.2)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(i, size: 14, color: Color(0xFF38BDF8)),
        SizedBox(width: 6),
        Text(l, style: TextStyle(color: Color(0xFF38BDF8), fontSize: 12, fontWeight: FontWeight.w500)),
      ]),
    ),
  );

  // ── View Toggle ──
  Widget _buildViewToggle() => Padding(
    padding: EdgeInsets.symmetric(horizontal: 32),
    child: Row(children: [
      for (var v in [
        {'k': 'list', 'l': '列表', 'i': Icons.list},
        {'k': 'month', 'l': '月', 'i': Icons.calendar_month},
        {'k': 'week', 'l': '周', 'i': Icons.date_range},
        {'k': 'day', 'l': '日', 'i': Icons.today},
      ])
        GestureDetector(
          onTap: () => _setView(v['k'] as String),
          child: Container(
            padding: EdgeInsets.only(bottom: 10),
            margin: EdgeInsets.only(right: 24),
            decoration: BoxDecoration(border: Border(bottom: BorderSide(
              color: _view == v['k'] ? Color(0xFF38BDF8) : Colors.transparent, width: 2,
            ))),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(v['i'] as IconData, size: 14, color: _view == v['k'] ? Color(0xFF38BDF8) : AppTheme.textMuted),
              SizedBox(width: 4),
              Text(v['l'] as String, style: TextStyle(
                color: _view == v['k'] ? Color(0xFF38BDF8) : AppTheme.textMuted,
                fontSize: 12, fontWeight: FontWeight.w500,
              )),
            ]),
          ),
        ),
    ]),
  );

  // ── Filters ──
  Widget _buildFilters() => Padding(
    padding: EdgeInsets.fromLTRB(32, 8, 32, 8),
    child: Row(children: [
      Expanded(flex: 2, child: _filterInput('搜索...', _search, _onSearch)),
      SizedBox(width: 8),
      _dd({'': '全部来源', 'manual': '手工', 'content': '内容', 'series': '专题', 'brainstorm': '脑暴'}, _fs, (v) { _fs = v; _load(); }),
      SizedBox(width: 8),
      _dd({'': '全部优先级', 'high': '高', 'medium': '中', 'low': '低'}, _fp, (v) { _fp = v; _load(); }),
      SizedBox(width: 8),
      _dd({'': '全部状态', 'todo': '待处理', 'in_progress': '进行中', 'done': '已完成'}, _fst, (v) { _fst = v; _load(); }),
      SizedBox(width: 12),
      Text('${_tasks.length} 项', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
    ]),
  );

  Widget _filterInput(String h, String v, Function(String) cb) => Container(
    height: 32, padding: EdgeInsets.symmetric(horizontal: 8),
    decoration: BoxDecoration(color: Color(0xFF141518), borderRadius: BorderRadius.circular(8), border: Border.all(color: Color(0xFF141518))),
    child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
      Icon(Icons.search, size: 13, color: AppTheme.textMuted),
      SizedBox(width: 4),
      Expanded(child: TextField(
        controller: TextEditingController(text: v)..selection = TextSelection.collapsed(offset: v.length),
        style: TextStyle(color: AppTheme.textPrimary, fontSize: 12),
        decoration: InputDecoration(hintText: h, hintStyle: TextStyle(color: AppTheme.textMuted, fontSize: 12), border: InputBorder.none, isDense: true, contentPadding: EdgeInsets.zero, filled: true, fillColor: Color(0xFF141518)),
        onChanged: cb,
      )),
    ]),
  );

  Widget _dd(Map<String,String> o, String v, Function(String) cb) => Container(
    height: 32, padding: EdgeInsets.symmetric(horizontal: 8),
    decoration: BoxDecoration(color: Color(0xFF141518), borderRadius: BorderRadius.circular(8), border: Border.all(color: Color(0xFF2A2B30))),
    child: DropdownButtonHideUnderline(child: DropdownButton<String>(
      value: o.containsKey(v) ? v : '', dropdownColor: Color(0xFF141518), isDense: true,
      icon: Icon(Icons.arrow_drop_down, color: AppTheme.textMuted, size: 16),
      style: TextStyle(color: AppTheme.textSecondary, fontSize: 12),
      items: o.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value, style: TextStyle(fontSize: 12)))).toList(),
      onChanged: (v) { if (v != null) cb(v); },
    )),
  );

  // ── Content ──
  Widget _buildContent() {
    if (_loading) return Center(child: CircularProgressIndicator(color: AppTheme.accent));
    if (_error != null) return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
      Text(_error!, style: TextStyle(color: AppTheme.error, fontSize: 12)),
      SizedBox(height: 12), _btn('重试', Icons.refresh, _load),
    ]));
    switch (_view) {
      case 'list': return _buildList();
      case 'month': return _buildMonth();
      case 'week': return _buildWeek();
      case 'day': return _buildDay();
      default: return SizedBox();
    }
  }

  // ── List View ──
  Widget _buildList() {
    if (_tasks.isEmpty) return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
      Text('暂无待办', style: TextStyle(color: AppTheme.textMuted, fontSize: 14)),
      SizedBox(height: 4), Text('点击新建添加事务', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
    ]));
    return ListView(padding: EdgeInsets.symmetric(horizontal: 32), children: [
      SizedBox(height: 4),
      Container(
        decoration: BoxDecoration(color: Color(0xFF141518), borderRadius: BorderRadius.circular(12), border: Border.all(color: Color(0xFF2A2B30))),
        child: Column(children: _tasks.asMap().entries.map((e) => _taskRow(e.value, e.key > 0)).toList()),
      ),
    ]);
  }

  Widget _taskRow(Map<String,dynamic> t, bool div) {
    var ti = t['title'] ?? '(无标题)', st = t['status'], sr = t['source'] ?? 'manual';
    var pr = t['priority'] ?? 'medium', du = t['due_date'];
    return InkWell(
      onTap: () => _openDetail(t['id']),
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(border: div ? Border(top: BorderSide(color: Color(0xFF2A2B30))) : null),
        child: Row(children: [
          Container(
            padding: EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(color: (_SRC_C[sr] ?? _SRC_C['manual'])!.withOpacity(0.15), borderRadius: BorderRadius.circular(4)),
            child: Text(_SRC_L[sr] ?? '手工', style: TextStyle(color: _SRC_C[sr] ?? _SRC_C['manual'], fontSize: 10, fontWeight: FontWeight.w500)),
          ),
          SizedBox(width: 12),
          Expanded(child: Text(ti, style: TextStyle(
            color: st == 'done' ? AppTheme.textMuted : AppTheme.textSecondary, fontSize: 13,
            decoration: st == 'done' ? TextDecoration.lineThrough : null,
          ), overflow: TextOverflow.ellipsis)),
          if (du != null && du.toString().isNotEmpty) ...[
            SizedBox(width: 12),
            Text(du.toString(), style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
          ],
          SizedBox(width: 12),
          Text(_PRI_L[pr] ?? pr, style: TextStyle(color: _PRI_C[pr] ?? AppTheme.textMuted, fontSize: 10)),
          SizedBox(width: 10),
          Row(mainAxisSize: MainAxisSize.min, children: _ST_O.map((s) {
            var a = st == s;
            return GestureDetector(
              onTap: a ? null : () => _updateStatus(t['id'], s),
              child: Container(
                margin: EdgeInsets.only(left: 4), padding: EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: a ? _stc(s).withOpacity(0.15) : Colors.transparent,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: a ? _stc(s).withOpacity(0.25) : Color(0xFF3A3B40).withOpacity(0.3)),
                ),
                child: Text(_ST_L[s]!, style: TextStyle(color: a ? _stc(s) : AppTheme.textMuted, fontSize: 10, fontWeight: FontWeight.w500)),
              ),
            );
          }).toList()),
        ]),
      ),
    );
  }

  // ── Calendar shared ──
  Widget _calNav(String t, VoidCallback p, VoidCallback n) => Row(children: [
    IconButton(onPressed: p, icon: Icon(Icons.chevron_left, color: AppTheme.textMuted, size: 20), padding: EdgeInsets.zero, constraints: BoxConstraints()),
    Expanded(child: Center(child: Text(t, style: TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w600)))),
    IconButton(onPressed: n, icon: Icon(Icons.chevron_right, color: AppTheme.textMuted, size: 20), padding: EdgeInsets.zero, constraints: BoxConstraints()),
  ]);

  Widget _statusPill(String? s) => Container(
    padding: EdgeInsets.symmetric(horizontal: 8, vertical: 2),
    decoration: BoxDecoration(color: _stc(s).withOpacity(0.12), borderRadius: BorderRadius.circular(10), border: Border.all(color: _stc(s).withOpacity(0.2))),
    child: Text(_ST_L[s] ?? s ?? '', style: TextStyle(color: _stc(s), fontSize: 10, fontWeight: FontWeight.w500)),
  );

  Widget _calDayCell(DateTime d, List<Map<String,dynamic>> dTasks, String today) {
    var ds = _fd(d), other = d.month - 1 != _mo, isSel = ds == _sd, isToday = ds == today;
    return Column(children: [
      Text('${d.day}', style: TextStyle(
        color: isToday ? Color(0xFF38BDF8) : (isSel ? Color(0xFF38BDF8) : (other ? AppTheme.textMuted : AppTheme.textSecondary)),
        fontSize: 10, fontWeight: isToday ? FontWeight.w700 : FontWeight.w400,
      )),
      ...dTasks.asMap().entries.take(3).map((e) {
        var t = e.value, i = e.key;
        return Container(
          width: double.infinity, margin: EdgeInsets.only(top: 2), padding: EdgeInsets.symmetric(horizontal: 2, vertical: 6),
          decoration: BoxDecoration(color: _tc(i).withOpacity(0.12), borderRadius: BorderRadius.circular(2)),
          child: Text(t['title'] ?? '', style: TextStyle(color: _tc(i), fontSize: 10), maxLines: 1, overflow: TextOverflow.ellipsis),
        );
      }),
      if (dTasks.length > 3) Text('+${dTasks.length - 3}', style: TextStyle(color: AppTheme.textMuted, fontSize: 7)),
    ]);
  }

  Widget _dayTaskList(String ds) {
    var items = _tod(ds), d = DateTime.tryParse(ds) ?? DateTime.now();
    if (items.isEmpty) return Container(
      padding: EdgeInsets.all(24),
      decoration: BoxDecoration(color: Color(0xFF141518), borderRadius: BorderRadius.circular(12), border: Border.all(color: Color(0xFF2A2B30))),
      child: Center(child: Text('当日无待办', style: TextStyle(color: AppTheme.textMuted, fontSize: 12))),
    );
    return Container(
      padding: EdgeInsets.all(16),
      decoration: BoxDecoration(color: Color(0xFF141518), borderRadius: BorderRadius.circular(12), border: Border.all(color: Color(0xFF2A2B30))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text('${d.year}年${d.month}月${d.day}日 周${_WD[d.weekday-1]}', style: TextStyle(color: AppTheme.textSecondary, fontSize: 13, fontWeight: FontWeight.w600)),
          SizedBox(width: 8), Text('${items.length} 项', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
          Spacer(), GestureDetector(onTap: () => _openCreate(dueDate: ds), child: Icon(Icons.add, color: Color(0xFF38BDF8), size: 18)),
        ]),
        SizedBox(height: 12),
        ...items.map((t) => InkWell(
          onTap: () => _openDetail(t['id']),
          child: Padding(
            padding: EdgeInsets.symmetric(vertical: 6),
            child: Row(children: [
              Text(_PRI_L[t['priority']] ?? '', style: TextStyle(color: _PRI_C[t['priority']], fontSize: 10)),
              SizedBox(width: 10),
              Expanded(child: Text(t['title'] ?? '', style: TextStyle(
                color: t['status'] == 'done' ? AppTheme.textMuted : AppTheme.textSecondary, fontSize: 13,
                decoration: t['status'] == 'done' ? TextDecoration.lineThrough : null,
              ))),
              _statusPill(t['status']),
            ]),
          ),
        )),
      ]),
    );
  }

  // ── Month View ──
  Widget _buildMonth() {
    var first = DateTime(_y, _mo + 1, 1), start = _gws(first);
    var days = List.generate(42, (i) => start.add(Duration(days: i)));
    var today = _fd(DateTime.now());
    return SingleChildScrollView(padding: EdgeInsets.all(32), child: Column(children: [
      _calNav('$_y年${_mo+1}月', () => _navMonth(-1), () => _navMonth(1)),
      SizedBox(height: 16),
      Container(
        padding: EdgeInsets.all(16),
        decoration: BoxDecoration(color: Color(0xFF141518), borderRadius: BorderRadius.circular(12), border: Border.all(color: Color(0xFF2A2B30))),
        child: Column(children: [
          Row(children: _WD.map((l) => Expanded(child: Center(child: Text(l, style: TextStyle(color: AppTheme.textMuted, fontSize: 11))))).toList()),
          SizedBox(height: 8),
          ...List.generate(6, (r) => Padding(
            padding: EdgeInsets.only(top: r > 0 ? 6 : 0),
            child: SizedBox(height: 160, child: Row(children: List.generate(7, (c) {
              var d = days[r * 7 + c], ds = _fd(d), dTasks = _tod(ds);
              var other = d.month - 1 != _mo, isSel = ds == _sd, isToday = ds == today;
              return Expanded(child: GestureDetector(
                onTap: () => setState(() => _sd = ds),
                child: Container(
                  margin: EdgeInsets.all(2), padding: EdgeInsets.all(3),
                  decoration: BoxDecoration(
                    color: isSel ? Color(0xFF0EA5E9).withOpacity(0.2) : other ? Colors.transparent : Color(0xFF0B0C10),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: isToday ? Color(0xFF38BDF8) : (isSel ? Color(0xFF38BDF8) : (other ? Colors.transparent : Color(0xFF2A2B30))), width: isToday ? 1.5 : 1.0),
                  ),
                  child: _calDayCell(d, dTasks, today),
                ),
              ));
            }))),
          )),
        ]),
      ),
      SizedBox(height: 16), _dayTaskList(_sd),
    ]));
  }

  // ── Week View ──
  Widget _buildWeek() {
    var days = List.generate(7, (i) => _ws.add(Duration(days: i)));
    var today = _fd(DateTime.now());
    return SingleChildScrollView(padding: EdgeInsets.all(32), child: Column(children: [
      _calNav('${_fd(_ws)} - ${_fd(_ws.add(Duration(days: 6)))}', () => _navWeek(-1), () => _navWeek(1)),
      SizedBox(height: 16),
      SizedBox(height: 160, child: Row(children: days.map((d) {
        var ds = _fd(d), dTasks = _tod(ds), isToday = ds == today;
        return Expanded(child: GestureDetector(
          onTap: () => setState(() => _sd = ds),
          child: Container(
            margin: EdgeInsets.symmetric(horizontal: 3), padding: EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: ds == _sd ? Color(0xFF0EA5E9).withOpacity(0.15) : Color(0xFF141518),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: isToday ? Color(0xFF38BDF8) : (ds == _sd ? Color(0xFF38BDF8) : Color(0xFF2A2B30)), width: isToday ? 1.5 : 1.0),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${_WD[d.weekday-1]} ${d.day}', style: TextStyle(
                color: isToday ? Color(0xFF38BDF8) : (ds == _sd ? Color(0xFF38BDF8) : AppTheme.textSecondary), fontSize: 11,
                fontWeight: isToday ? FontWeight.w700 : FontWeight.w400,
              )),
              SizedBox(height: 4),
              ...dTasks.asMap().entries.take(5).map((e) {
                var t = e.value, i = e.key;
                return Padding(
                  padding: EdgeInsets.only(bottom: 2),
                  child: Text(t['title'] ?? '', style: TextStyle(color: _tc(i), fontSize: 9), maxLines: 1, overflow: TextOverflow.ellipsis),
                );
              }),
            ]),
          ),
        ));
      }).toList())),
      SizedBox(height: 16), _dayTaskList(_sd),
    ]));
  }

  // ── Day View ──
  Widget _buildDay() {
    var d = DateTime(_y, _mo + 1, _d), ds = _fd(d);
    return Padding(padding: EdgeInsets.all(32), child: Column(children: [
      _calNav('$_y年${_mo+1}月${_d}日 周${_WD[d.weekday-1]}', () => _navDay(-1), () => _navDay(1)),
      SizedBox(height: 16), _dayTaskList(ds),
    ]));
  }

  // ── Detail Overlay ──
  Widget _buildDetailOverlay() => GestureDetector(
    onTap: () => setState(() { _detail = null; _edit = false; }),
    child: Container(color: Colors.black54, child: Align(alignment: Alignment.center, child: Container(
      width: 400, color: Color(0xFF141518),
      child: Material(child: Container(color: Color(0xFF141518), child: SingleChildScrollView(
        padding: EdgeInsets.all(20),
        child: _edit ? _buildEditForm() : _buildDetailView(),
      ))),
    ))),
  );

  Widget _buildDetailView() {
    var d = _detail!;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [Spacer(), GestureDetector(onTap: () => setState(() { _detail = null; _edit = false; }), child: Icon(Icons.close, color: AppTheme.textMuted, size: 18))]),
      SizedBox(height: 8),
      Text(d['title'] ?? '', style: TextStyle(color: AppTheme.textPrimary, fontSize: 17, fontWeight: FontWeight.w600)),
      if (d['description'] != null && (d['description'] as String).isNotEmpty) ...[
        SizedBox(height: 12),
        Text(d['description'], style: TextStyle(color: AppTheme.textSecondary, fontSize: 13, height: 1.5)),
      ],
      SizedBox(height: 16),
      _metaRow('优先级', _PRI_L[d['priority']] ?? '', _PRI_C[d['priority']] ?? AppTheme.textMuted),
      _metaRow('截止日', d['due_date'] ?? '无', AppTheme.textSecondary),
      Row(children: [
        SizedBox(width: 68, child: Text('状态', style: TextStyle(color: AppTheme.textMuted, fontSize: 12))),
        ..._ST_O.map((s) => GestureDetector(
          onTap: d['status'] == s ? null : () => _updateStatus(d['id'], s),
          child: Container(
            margin: EdgeInsets.only(right: 6), padding: EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: d['status'] == s ? _stc(s).withOpacity(0.15) : Colors.transparent,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: d['status'] == s ? _stc(s).withOpacity(0.25) : Color(0xFF2A2B30)),
            ),
            child: Text(_ST_L[s]!, style: TextStyle(color: d['status'] == s ? _stc(s) : AppTheme.textMuted, fontSize: 11)),
          ),
        )),
      ]),
      SizedBox(height: 4),
      Text(_fmt(d['created_at']), style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
      SizedBox(height: 20),
      Row(children: [
        Expanded(child: _btnSmall('编辑', Color(0xFFF59E0B), _startEdit)),
        SizedBox(width: 8),
        Expanded(child: _btnSmall(_judge ? '分析中...' : 'AI 分析', Color(0xFF38BDF8), _judge ? null : _runJudge)),
      ]),
      SizedBox(height: 8),
      Center(child: GestureDetector(onTap: () => _deleteTask(d['id']), child: Text('删除', style: TextStyle(color: AppTheme.error, fontSize: 12)))),
    ]);
  }

  Widget _metaRow(String l, String v, Color c) => Padding(
    padding: EdgeInsets.only(bottom: 6),
    child: Row(children: [
      SizedBox(width: 68, child: Text(l, style: TextStyle(color: AppTheme.textMuted, fontSize: 12))),
      Text(v, style: TextStyle(color: c, fontSize: 12)),
    ]),
  );

  Widget _btnSmall(String l, Color c, VoidCallback? f) => GestureDetector(
    onTap: f,
    child: Container(
      padding: EdgeInsets.symmetric(vertical: 10), alignment: Alignment.center,
      decoration: BoxDecoration(color: c.withOpacity(0.1), borderRadius: BorderRadius.circular(8), border: Border.all(color: c.withOpacity(0.2))),
      child: Text(l, style: TextStyle(color: c, fontSize: 12, fontWeight: FontWeight.w500)),
    ),
  );

  // ── Edit Form ──
  Widget _buildEditForm() => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Row(children: [
      Text('编辑待办', style: TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w600)),
      Spacer(), TextButton(onPressed: () => setState(() => _edit = false), child: Text('取消')),
    ]),
    SizedBox(height: 12), _textField(_et, '标题'), SizedBox(height: 10),
    _textField(_ed, '描述（可选）', maxLines: 4), SizedBox(height: 12),
    Row(children: [
      Expanded(child: _editDropdown('优先级', {'high': '高', 'medium': '中', 'low': '低'}, _ep, (v) => _ep = v!)),
      SizedBox(width: 8),
      Expanded(child: _editDropdown('状态', {'todo': '待处理', 'in_progress': '进行中', 'done': '已完成'}, _es, (v) => _es = v!)),
    ]),
    SizedBox(height: 12), _dateField(_edd, (v) => _edd = v), SizedBox(height: 16),
    SizedBox(width: double.infinity, child: _btn('保存', Icons.check, _saveEdit)),
  ]);

  Widget _textField(TextEditingController c, String h, {int maxLines = 1}) => TextField(
    controller: c, maxLines: maxLines, style: TextStyle(color: AppTheme.textPrimary, fontSize: 13),
    decoration: InputDecoration(
      hintText: h, hintStyle: TextStyle(color: AppTheme.textMuted), filled: true, fillColor: Color(0xFF0B0C10),
      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: Color(0xFF2A2B30))),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: Color(0xFF2A2B30))),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: Color(0xFF38BDF8))),
    ),
  );

  Widget _editDropdown(String l, Map<String,String> o, String v, Function(String?) cb) => Column(
    crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(l, style: TextStyle(color: AppTheme.textMuted, fontSize: 11)), SizedBox(height: 4),
      Container(
        height: 36, padding: EdgeInsets.symmetric(horizontal: 8),
        decoration: BoxDecoration(color: Color(0xFF0B0C10), borderRadius: BorderRadius.circular(8), border: Border.all(color: Color(0xFF2A2B30))),
        child: DropdownButtonHideUnderline(child: DropdownButton<String>(
          value: v, dropdownColor: Color(0xFF141518), isDense: true,
          style: TextStyle(color: AppTheme.textPrimary, fontSize: 12),
          items: o.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value))).toList(),
          onChanged: cb,
        )),
      ),
    ],
  );

  Widget _dateField(String v, Function(String) cb) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text('截止日', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)), SizedBox(height: 4),
    TextField(
      controller: TextEditingController(text: v)..selection = TextSelection.collapsed(offset: v.length),
      style: TextStyle(color: AppTheme.textPrimary, fontSize: 13),
      decoration: InputDecoration(
        hintText: 'YYYY-MM-DD', hintStyle: TextStyle(color: AppTheme.textMuted), filled: true, fillColor: Color(0xFF0B0C10),
        contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: Color(0xFF2A2B30))),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: Color(0xFF2A2B30))),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: Color(0xFF38BDF8))),
      ),
      onChanged: cb,
    ),
  ]);

  // ── Create Overlay ──
  Widget _buildCreateOverlay() => GestureDetector(
    onTap: _closeCreate,
    child: Container(color: Colors.black54, alignment: Alignment.center, child: GestureDetector(
      onTap: () {},
      child: Container(
        width: 420, margin: EdgeInsets.all(32), padding: EdgeInsets.all(24),
        decoration: BoxDecoration(color: Color(0xFF141518), borderRadius: BorderRadius.circular(16), border: Border.all(color: Color(0xFF2A2B30))),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('新建待办', style: TextStyle(color: AppTheme.textPrimary, fontSize: 15, fontWeight: FontWeight.w600)),
          SizedBox(height: 16), _textField(_nt, '标题 *'), SizedBox(height: 10),
          _textField(_ndesc, '描述（可选）', maxLines: 3), SizedBox(height: 12),
          Row(children: [
            Expanded(child: _editDropdown('优先级', {'high': '高', 'medium': '中', 'low': '低'}, _np, (v) => _np = v!)),
            SizedBox(width: 8),
            Expanded(child: _dateField(_ndd, (v) => _ndd = v)),
          ]),
          SizedBox(height: 16),
          Row(mainAxisAlignment: MainAxisAlignment.end, children: [
            TextButton(onPressed: _closeCreate, child: Text('取消', style: TextStyle(color: AppTheme.textMuted))),
            SizedBox(width: 8),
            ElevatedButton(
              onPressed: _nt.text.trim().isEmpty ? null : _createTask,
              style: ElevatedButton.styleFrom(
                backgroundColor: Color(0xFF0EA5E9).withOpacity(0.15),
                foregroundColor: Color(0xFF38BDF8),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                side: BorderSide(color: Color(0xFF0EA5E9), width: 0.5),
              ),
              child: Text('创建'),
            ),
          ]),
        ]),
      ),
    )),
  );

  String _fmt(dynamic v) {
    if (v == null) return '';
    try {
      var d = DateTime.parse(v.toString());
      return '${d.month}月${d.day}日 ${d.hour.toString().padLeft(2,'0')}:${d.minute.toString().padLeft(2,'0')}';
    } catch (_) { return ''; }
  }
}

extension _S on String? { String? get nE => this != null && this!.isNotEmpty ? this : null; }
