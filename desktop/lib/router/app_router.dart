import 'package:go_router/go_router.dart';
import '../widgets/shell.dart';
import '../pages/dashboard/dashboard_page.dart';
import '../pages/ingest/ingest_page.dart';
import '../pages/events/events_page.dart';
import '../pages/events/event_detail_page.dart';
import '../pages/sources/sources_page.dart';
import '../pages/digest/digest_page.dart';
import '../pages/brainstorm/brainstorm_page.dart';
import '../pages/brainstorm/brainstorm_detail_page.dart';
import '../pages/tasks/tasks_page.dart';
import '../pages/series/series_page.dart';
import '../pages/series/series_detail_page.dart';
import '../pages/knowledge_graph/knowledge_graph_page.dart';
import '../pages/industry_chains/industry_chains_page.dart';
import '../pages/study/study_page.dart';
import '../pages/study/study_detail_page.dart';
import '../pages/toolbox/toolbox_page.dart';
import '../pages/ingest/queue_page.dart';
import '../pages/system_doc/system_doc_page.dart';
import '../pages/system_settings/system_settings_page.dart';

final appRouter = GoRouter(
  initialLocation: '/',
  routes: [
    ShellRoute(
      builder: (context, state, child) => AppShell(child: child),
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => const DashboardPage(),
        ),
        GoRoute(
          path: '/ingest',
          builder: (context, state) => const IngestPage(),
        ),
        GoRoute(
          path: '/events',
          builder: (context, state) => const EventsPage(),
          routes: [
            GoRoute(
              path: ':id',
              builder: (context, state) =>
                  EventDetailPage(id: int.parse(state.pathParameters['id']!)),
            ),
          ],
        ),
        GoRoute(
          path: '/sources',
          builder: (context, state) => const SourcesPage(),
        ),
        GoRoute(
          path: '/digest',
          builder: (context, state) => const DigestPage(),
        ),
        GoRoute(
          path: '/brainstorm',
          builder: (context, state) => const BrainstormPage(),
          routes: [
            GoRoute(
              path: ':id',
              builder: (context, state) =>
                  BrainstormDetailPage(id: state.pathParameters['id']!),
            ),
          ],
        ),
        GoRoute(
          path: '/tasks',
          builder: (context, state) => const TasksPage(),
        ),
        GoRoute(
          path: '/series',
          builder: (context, state) => const SeriesPage(),
          routes: [
            GoRoute(
              path: ':id',
              builder: (context, state) =>
                  SeriesDetailPage(id: int.parse(state.pathParameters['id']!)),
            ),
          ],
        ),
        GoRoute(
          path: '/knowledge-graph',
          builder: (context, state) => const KnowledgeGraphPage(),
        ),
        GoRoute(
          path: '/chains',
          builder: (context, state) => const IndustryChainsPage(),
        ),
        GoRoute(
          path: '/study',
          builder: (context, state) => const StudyPage(),
          routes: [
            GoRoute(
              path: ':id',
              builder: (context, state) =>
                  StudyDetailPage(id: state.pathParameters['id']!),
            ),
          ],
        ),
        GoRoute(
          path: '/tools',
          builder: (context, state) => const ToolboxPage(),
        ),
        GoRoute(
          path: '/queue',
          builder: (context, state) => const QueuePage(),
        ),
        GoRoute(
          path: '/system',
          builder: (context, state) => const SystemDocPage(),
        ),
        GoRoute(
          path: '/settings',
          builder: (context, state) => const SystemSettingsPage(),
        ),
      ],
    ),
  ],
);
