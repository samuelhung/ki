import 'package:dio/dio.dart';
import 'config_service.dart';

/// 知几后端 API 客户端
/// 
/// 启动时从 ConfigService 读取后端地址，默认 http://127.0.0.1:9120
/// 可通过系统设置页修改后端地址（如指向局域网内另一台机器）
class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  factory ApiClient() => _instance;

  late Dio dio;
  String _baseUrl = 'http://127.0.0.1:9120';

  ApiClient._internal() {
    dio = _createDio(_baseUrl);
  }

  Dio _createDio(String baseUrl) {
    return Dio(BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
      headers: {'Content-Type': 'application/json'},
      validateStatus: (status) => status != null && status < 500,
    ));
  }

  /// 初始化：从配置文件读取后端地址
  Future<void> initialize() async {
    _baseUrl = await ConfigService.getBackendUrl();
    dio = _createDio(_baseUrl);
  }

  /// 修改后端地址并持久化
  Future<void> setBackendUrl(String url) async {
    final cleanUrl = url.endsWith('/') ? url.substring(0, url.length - 1) : url;
    await ConfigService.setBackendUrl(cleanUrl);
    _baseUrl = cleanUrl;
    dio = _createDio(cleanUrl);
  }

  /// 当前后端地址（只读）
  String get backendUrl => _baseUrl;

  // ---- 健康检查 ----
  Future<bool> checkHealth() async {
    try {
      final resp = await dio.get('/api/health');
      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // ---- 仪表盘 ----
  Future<Map<String, dynamic>> getDashboardSummary() async {
    final resp = await dio.get('/api/dashboard/summary');
    return resp.data;
  }

  Future<List<dynamic>> getDashboardTrend({int days = 7}) async {
    final resp = await dio.get('/api/dashboard/trend', queryParameters: {'days': days});
    return resp.data;
  }

  // ---- 事件 ----
  Future<Map<String, dynamic>> getEvents({
    int offset = 0,
    int limit = 50,
    String? sourceId,
    String? topic,
    String? search,
    bool includeCount = false,
  }) async {
    final params = <String, dynamic>{'offset': offset, 'limit': limit};
    if (sourceId != null) params['source_id'] = sourceId;
    if (topic != null) params['topic'] = topic;
    if (search != null) params['search'] = search;
    if (includeCount) params['count'] = 1;

    final resp = await dio.get('/api/events', queryParameters: params);
    final data = resp.data;

    if (data is Map<String, dynamic>) return data;
    if (data is List) return {'items': data, 'total': data.length};
    return {'items': [], 'total': 0};
  }

  Future<Map<String, dynamic>> getEvent(int id) async {
    final resp = await dio.get('/api/events/$id');
    return resp.data;
  }

  // ---- 来源 ----
  Future<List<dynamic>> getSources() async {
    final resp = await dio.get('/api/sources');
    final data = resp.data;
    if (data is List) return data;
    return [];
  }

  // ---- 摘要 ----
  Future<Map<String, dynamic>> getDigests({int offset = 0, int limit = 30}) async {
    final resp = await dio.get('/api/digest/latest',
        queryParameters: {'offset': offset, 'limit': limit});
    final data = resp.data;
    if (data is Map<String, dynamic>) return data;
    if (data is List) return {'items': data, 'total': data.length};
    return {'items': [], 'total': 0};
  }

  // ---- 头脑风暴 ----
  Future<Map<String, dynamic>> getBrainstorms({int offset = 0, int limit = 30, String? topic}) async {
    final params = <String, dynamic>{'offset': offset, 'limit': limit};
    if (topic != null) params['topic'] = topic;
    final resp = await dio.get('/api/brainstorm', queryParameters: params);
    final data = resp.data;
    if (data is Map<String, dynamic>) return data;
    if (data is List) return {'items': data, 'total': data.length};
    return {'items': [], 'total': 0};
  }

  Future<Map<String, dynamic>> getBrainstorm(String id) async {
    final resp = await dio.get('/api/brainstorm/$id');
    return resp.data;
  }

  Future<Map<String, dynamic>> getBrainstormTopicCounts() async {
    final resp = await dio.get('/api/brainstorm/topic-counts');
    return resp.data;
  }

  Future<Map<String, dynamic>> createBrainstorm(String question) async {
    final resp = await dio.post('/api/brainstorm', data: {'question': question});
    return resp.data;
  }

  Future<void> deleteBrainstorm(String id) async {
    await dio.delete('/api/brainstorm/$id');
  }

  Future<void> batchDeleteBrainstorms(List<String> ids) async {
    await dio.post('/api/brainstorm/batch-delete', data: {'question_ids': ids});
  }

  // ---- 任务 ----
  Future<Map<String, dynamic>> getTasks({
    int offset = 0, int limit = 30,
    String? status, String? source, String? priority, String? search,
  }) async {
    final params = <String, dynamic>{'offset': offset, 'limit': limit};
    if (status != null && status.isNotEmpty) params['status'] = status;
    if (source != null && source.isNotEmpty) params['source'] = source;
    if (priority != null && priority.isNotEmpty) params['priority'] = priority;
    if (search != null && search.isNotEmpty) params['search'] = search;
    final resp = await dio.get('/api/tasks', queryParameters: params);
    final data = resp.data;
    if (data is Map<String, dynamic>) return data;
    if (data is List) return {'items': data, 'total': data.length};
    return {'items': [], 'total': 0};
  }

  Future<Map<String, dynamic>> getTask(String id) async {
    final resp = await dio.get('/api/tasks/$id');
    return resp.data;
  }

  Future<Map<String, dynamic>> createTask(Map<String, dynamic> body) async {
    final resp = await dio.post('/api/tasks', data: body);
    return resp.data;
  }

  Future<Map<String, dynamic>> updateTask(String id, Map<String, dynamic> body) async {
    final resp = await dio.put('/api/tasks/$id', data: body);
    return resp.data;
  }

  Future<void> deleteTask(String id) async {
    await dio.delete('/api/tasks/$id');
  }

  Future<Map<String, dynamic>> judgeTask(String id) async {
    final resp = await dio.post('/api/tasks/$id/judge');
    return resp.data;
  }

  Future<List<dynamic>> getTasksDue(String fromDate, String toDate) async {
    final resp = await dio.get('/api/tasks/due',
        queryParameters: {'from_date': fromDate, 'to_date': toDate});
    final data = resp.data;
    if (data is List) return data;
    if (data is Map<String, dynamic>) return data['items'] as List<dynamic>? ?? [];
    return [];
  }

  Future<Map<String, dynamic>> getTaskStats() async {
    final resp = await dio.get('/api/tasks/stats');
    return resp.data;
  }

  // ---- 专题 ----
  Future<Map<String, dynamic>> getSeriesList({int offset = 0, int limit = 30}) async {
    final resp = await dio.get('/api/ingest/series',
        queryParameters: {'offset': offset, 'limit': limit});
    final data = resp.data;
    if (data is Map<String, dynamic>) return data;
    if (data is List) return {'items': data, 'total': data.length};
    return {'items': [], 'total': 0};
  }

  // ---- 产业链 ----
  Future<Map<String, dynamic>> getChains() async {
    final resp = await dio.get('/api/chains');
    return resp.data;
  }

  Future<Map<String, dynamic>> getChainHintsCount() async {
    final resp = await dio.get('/api/chains/hints/count');
    return resp.data;
  }

  // ---- 知识图谱 ----
  Future<Map<String, dynamic>> getKnowledgeGraph() async {
    final resp = await dio.get('/api/entities/graph');
    return resp.data;
  }

  // ---- 辅导中心 ----
  Future<Map<String, dynamic>> getStudyItems({int offset = 0, int limit = 30}) async {
    final resp = await dio.get('/api/study',
        queryParameters: {'offset': offset, 'limit': limit});
    return resp.data;
  }

  // ---- 系统 ----
  Future<Map<String, dynamic>> getSystemInfo() async {
    final resp = await dio.get('/api/system/info');
    return resp.data;
  }

  Future<Map<String, dynamic>> getConfig() async {
    final resp = await dio.get('/api/config');
    return resp.data;
  }

  // 系统配置（AI 参数）
  Future<Map<String, dynamic>> getSystemConfig() async {
    final resp = await dio.get('/api/system-config');
    return resp.data;
  }

  Future<bool> saveSystemConfig(Map<String, dynamic> config) async {
    final resp = await dio.put('/api/system-config', data: config);
    return resp.statusCode == 200;
  }

  // 数据库信息
  Future<Map<String, dynamic>> getDatabaseInfo() async {
    final resp = await dio.get('/api/system/database');
    return resp.data;
  }

  // 系统日志
  Future<Map<String, dynamic>> getLogs({
    String level = 'INFO',
    int limit = 500,
    String? search,
  }) async {
    final params = <String, dynamic>{'level': level, 'limit': limit};
    if (search != null && search.isNotEmpty) params['search'] = search;
    final resp = await dio.get('/api/logs', queryParameters: params);
    return resp.data;
  }

  // Prompt 模板
  Future<Map<String, dynamic>> getPrompts() async {
    final resp = await dio.get('/api/system/prompts');
    return resp.data;
  }
}
