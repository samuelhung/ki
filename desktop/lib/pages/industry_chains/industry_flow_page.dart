import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import '../../theme/app_theme.dart';
import '../../services/api_client.dart';

class IndustryFlowPage extends StatefulWidget {
  const IndustryFlowPage({super.key});

  @override
  State<IndustryFlowPage> createState() => _IndustryFlowPageState();
}

class _IndustryFlowPageState extends State<IndustryFlowPage> {
  final _api = ApiClient();
  WebViewController? _webCtrl;
  bool _loading = true;
  List<Map<String, dynamic>> _nodes = [];
  Map<String, dynamic>? _selectedNode;

  @override
  void initState() {
    super.initState();
    _fetchData();
  }

  Future<void> _fetchData() async {
    setState(() => _loading = true);
    try {
      final data = await _api.getChainNodes();
      final nodes = (data['nodes'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
      setState(() { _nodes = nodes; _loading = false; });
      if (_webCtrl != null) _render();
    } catch (_) {
      setState(() => _loading = false);
    }
  }

  void _render() {
    if (_nodes.isEmpty || _webCtrl == null) return;
    _webCtrl!.runJavaScript('window.renderFlow(${jsonEncode(_nodes)});');
  }

  String _buildHtml() {
    return '''
<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:#0B0C10;font-family:system-ui,sans-serif}
</style>
<script type="importmap">
{"imports":{"@xyflow/react":"https://esm.sh/@xyflow/react@12.6.0","react":"https://esm.sh/react@18.3.1","react-dom":"https://esm.sh/react-dom@18.3.1"}}
</script>
</head><body>
<div id="root" style="width:100%;height:100%"></div>
<script type="module">
import React,{useMemo,useCallback,useState}from'react';
import ReactDOM from'react-dom/client';
import{ReactFlow,Background,Controls,MiniMap,useNodesState,useEdgesState,Handle,Position}from'@xyflow/react';

const LEVEL_X={'原材料':80,'中间品':400,'零部件':720,'终端':1040};
const PALETTE=[
  {border:'#eab308',bg:'rgba(234,179,8,0.12)',edge:'#eab308'},
  {border:'#06b6d4',bg:'rgba(6,182,212,0.12)',edge:'#06b6d4'},
  {border:'#f59e0b',bg:'rgba(245,158,11,0.12)',edge:'#f59e0b'},
  {border:'#22c55e',bg:'rgba(34,197,94,0.12)',edge:'#22c55e'},
  {border:'#a855f7',bg:'rgba(168,85,247,0.12)',edge:'#a855f7'},
  {border:'#ef4444',bg:'rgba(239,68,68,0.12)',edge:'#ef4444'},
  {border:'#f97316',bg:'rgba(249,115,22,0.12)',edge:'#f97316'},
  {border:'#ec4899',bg:'rgba(236,72,153,0.12)',edge:'#ec4899'},
];
const CROSS_LINKS=[
  {fromName:'工业硅/硅料',toName:'硅晶圆',label:'电子级多晶硅'},
  {fromName:'光伏银浆',toName:'封装测试',label:'导电浆料共通'},
  {fromName:'负极材料（石墨/硅碳）',toName:'硅晶圆',label:'高纯石墨耗材'},
  {fromName:'封装测试',toName:'组件',label:'层压封装共通'},
  {fromName:'碳酸锂/氢氧化锂',toName:'光伏玻璃',label:'锂盐添加剂'},
];

let colorIdx=0;
const colorMap=new Map();
function getColors(chain){
  if(!colorMap.has(chain))colorMap.set(chain,colorIdx++);
  return PALETTE[colorMap.get(chain)%PALETTE.length];
}

function ChainNode({data}){
  const colors=getColors(data.chain);
  return React.createElement('div',{
    style:{background:colors.bg,borderColor:colors.border,minWidth:120,padding:'6px 12px',borderRadius:8,borderWidth:1,borderStyle:'solid',fontSize:10,cursor:'pointer'}
  },
    React.createElement(Handle,{type:'target',position:Position.Left,style:{background:colors.border}}),
    React.createElement('div',{style:{fontWeight:500,color:'#e5e7eb',fontSize:11,lineHeight:1.3}},data.label),
    React.createElement('div',{style:{fontSize:9,marginTop:2,color:colors.border}},data.node_type),
    React.createElement(Handle,{type:'source',position:Position.Right,style:{background:colors.border}})
  );
}
const nodeTypes={chainNode:ChainNode};

function App(){
  const[allNodes,setAllNodes]=useState([]);
  const[selectedNode,setSelectedNode]=useState(null);
  const[search,setSearch]=useState('');

  window.renderFlow=function(nodes){
    setAllNodes(nodes);
  };

  const nameToId=useMemo(()=>{
    const m={};
    allNodes.forEach(n=>{m[n.name]=n.id;});
    return m;
  },[allNodes]);

  const initialNodes=useMemo(()=>{
    const chains=new Map();
    allNodes.forEach(n=>{
      if(!chains.has(n.chain))chains.set(n.chain,[]);
      chains.get(n.chain).push(n);
    });
    const order=Array.from(chains.keys()).sort();
    const result=[];
    let y=0;
    order.forEach(name=>{
      const cn=chains.get(name)||[];
      cn.sort((a,b)=>(a.sort_order||0)-(b.sort_order||0));
      cn.forEach((n,i)=>{
        const x=LEVEL_X[n.node_type]||80;
        result.push({
          id:n.id,type:'chainNode',
          position:{x,y:y+i*85},
          data:{label:n.name,chain:n.chain,node_type:n.node_type}
        });
      });
      y+=cn.length*85+80;
    });
    return result;
  },[allNodes]);

  const initialEdges=useMemo(()=>{
    const edges=[];
    allNodes.forEach(n=>{
      try{
        const upstreamIds=typeof n.upstream_ids==='string'?JSON.parse(n.upstream_ids):n.upstream_ids||[];
        const colors=getColors(n.chain);
        upstreamIds.forEach(uid=>{
          edges.push({
            id:'intra-'+uid+'-'+n.id,
            source:uid,target:n.id,animated:true,
            style:{stroke:colors.edge,strokeWidth:1.5}
          });
        });
      }catch(e){}
    });
    CROSS_LINKS.forEach((link,i)=>{
      const fromId=nameToId[link.fromName];
      const toId=nameToId[link.toName];
      if(fromId&&toId){
        edges.push({
          id:'cross-'+i,source:fromId,target:toId,
          label:link.label,animated:false,
          style:{stroke:'#a855f7',strokeWidth:1.5,strokeDasharray:'6 4'},
          labelStyle:{fill:'#a78bfa',fontSize:9,fontWeight:500},
          labelBgStyle:{fill:'#141518',fillOpacity:0.9},
          labelBgPadding:[4,2],labelBgBorderRadius:2
        });
      }
    });
    return edges;
  },[allNodes,nameToId]);

  const matchIds=useMemo(()=>{
    if(!search.trim())return new Set();
    const q=search.toLowerCase();
    return new Set(allNodes.filter(n=>
      (n.name||'').toLowerCase().includes(q)||
      (n.node_type||'').toLowerCase().includes(q)||
      (n.chain||'').toLowerCase().includes(q)
    ).map(n=>n.id));
  },[allNodes,search]);

  const displayNodes=useMemo(()=>{
    if(!search.trim())return initialNodes;
    return initialNodes.map(n=>({...n,style:{opacity:matchIds.has(n.id)?1:0.15,transition:'opacity 0.2s'}}));
  },[initialNodes,search,matchIds]);

  const displayEdges=useMemo(()=>{
    if(!search.trim())return initialEdges;
    return initialEdges.map(e=>({
      ...e,style:{...e.style,opacity:(matchIds.has(e.source)||matchIds.has(e.target))?1:0.05,transition:'opacity 0.2s'}
    }));
  },[initialEdges,search,matchIds]);

  const[nodes,setNodes,onNodesChange]=useNodesState(displayNodes);
  const[edges,setEdges,onEdgesChange]=useEdgesState(displayEdges);

  React.useEffect(()=>{setNodes(displayNodes);},[displayNodes]);
  React.useEffect(()=>{setEdges(displayEdges);},[displayEdges]);

  const onNodeClick=useCallback((_e,node)=>{
    const found=allNodes.find(n=>n.id===node.id);
    if(found)window.flutterChannel.postMessage(JSON.stringify({type:'select',node:found}));
  },[allNodes]);

  const chains=Array.from(new Set(allNodes.map(n=>n.chain))).sort();

  return React.createElement('div',{style:{width:'100%',height:'100%',position:'relative',background:'#0B0C10'}},
    // Back button
    React.createElement('a',{
      href:'#',onClick:e=>{e.preventDefault();window.flutterChannel.postMessage(JSON.stringify({type:'back'}));},
      style:{position:'absolute',top:16,left:16,zIndex:20,display:'flex',alignItems:'center',gap:6,background:'#141518',border:'1px solid #2A2B30',borderRadius:8,padding:'6px 12px',fontSize:12,color:'#6B7280',textDecoration:'none',cursor:'pointer',boxShadow:'0 8px 32px rgba(0,0,0,0.4)'}
    },'← 返回产业链'),
    // Search bar
    React.createElement('div',{
      style:{position:'absolute',top:16,left:'50%',transform:'translateX(-50%)',zIndex:20,display:'flex',alignItems:'center',gap:8,background:'#141518',border:'1px solid #2A2B30',borderRadius:8,padding:'6px 12px',boxShadow:'0 8px 32px rgba(0,0,0,0.4)'}
    },
      React.createElement('input',{
        type:'text',value:search,onChange:e=>setSearch(e.target.value),
        placeholder:'搜索节点、类型、产业链...',
        style:{background:'transparent',fontSize:13,color:'#e5e7eb',outline:'none',border:'none',width:224}
      }),
      search&&React.createElement(React.Fragment,null,
        React.createElement('span',{style:{fontSize:11,color:'#6B7280'}},matchIds.size+' 个匹配'),
        React.createElement('button',{onClick:()=>setSearch(''),style:{background:'none',border:'none',color:'#6B7280',cursor:'pointer',fontSize:14}},'×')
      )
    ),
    React.createElement(ReactFlow,{
      nodes,edges,onNodesChange,onEdgesChange,onNodeClick,nodeTypes,
      fitView:true,fitViewOptions:{padding:0.3},minZoom:0.2,maxZoom:2,
      defaultViewport:{x:0,y:0,zoom:0.75},
      proOptions:{hideAttribution:true}
    },
      React.createElement(Background,{color:'#2A2B30',gap:20}),
      React.createElement(Controls,{style:{background:'#141518',border:'1px solid #2A2B30',borderRadius:8}}),
      React.createElement(MiniMap,{nodeColor:n=>getColors(n.data?.chain)?.border||'#666',style:{background:'#141518'},maskColor:'rgba(11,12,16,0.7)'})
    ),
    // Legend
    React.createElement('div',{
      style:{position:'absolute',bottom:16,left:16,zIndex:10,background:'#141518',border:'1px solid #2A2B30',borderRadius:8,padding:12}
    },
      React.createElement('div',{style:{fontSize:10,fontWeight:500,color:'#6B7280',marginBottom:8}},'图例'),
      chains.map(name=>{
        const c=getColors(name);
        return React.createElement('div',{key:name,style:{display:'flex',alignItems:'center',gap:8,marginBottom:4}},
          React.createElement('div',{style:{width:12,height:2,borderRadius:2,background:c.edge}}),
          React.createElement('span',{style:{fontSize:10,color:'#6B7280'}},name.replace('产业链',''))
        );
      }),
      React.createElement('div',{style:{display:'flex',alignItems:'center',gap:8}},
        React.createElement('div',{style:{width:12,height:2,borderRadius:2,background:'#a855f7'}}),
        React.createElement('span',{style:{fontSize:10,color:'#a855f7'}},'跨链连接')
      )
    ),
    // Detail panel
    selectedNode&&React.createElement(DetailPanel,{node:selectedNode,onClose:()=>setSelectedNode(null)})
  );
}

function DetailPanel({node,onClose}){
  const groups=useMemo(()=>{
    try{
      const d=typeof node.global_shares==='string'?JSON.parse(node.global_shares):node.global_shares||[];
      if(d&&d.groups)return{
        production:d.groups.production||[],supply:d.groups.supply||[],demand:d.groups.demand||[]
      };
      if(Array.isArray(d))return{production:d,supply:[],demand:[]};
    }catch(e){}
    return{production:[],supply:[],demand:[]};
  },[]);
  const allShares=[...groups.production,...groups.supply,...groups.demand];
  const uniqueCountries=[...new Set(allShares.map(s=>s.c))];
  const countryMap=new Map();
  allShares.forEach(s=>{
    const ex=countryMap.get(s.c);
    if(!ex){countryMap.set(s.c,s);return;}
    if((s.p+s.d+s.p_export_global+s.d_import_global)>(ex.p+ex.d+ex.p_export_global+ex.d_import_global))
      countryMap.set(s.c,s);
  });

  return React.createElement('div',{
    style:{position:'absolute',top:16,right:16,width:320,maxHeight:'80vh',overflowY:'auto',background:'#141518',border:'1px solid #2A2B30',borderRadius:12,padding:16,boxShadow:'0 16px 64px rgba(0,0,0,0.5)',zIndex:20}
  },
    React.createElement('div',{style:{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}},
      React.createElement('h3',{style:{fontSize:14,fontWeight:600,color:'white'}},node.name),
      React.createElement('button',{onClick:onClose,style:{background:'none',border:'none',color:'#6B7280',cursor:'pointer',fontSize:16}},'×')
    ),
    node.description&&React.createElement('p',{style:{fontSize:11,color:'#6B7280',marginBottom:12}},node.description),
    uniqueCountries.map(c=>{
      const s=countryMap.get(c);
      if(!s)return null;
      return React.createElement('div',{key:c,style:{background:'#0B0C10',border:'1px solid #2A2B30',borderRadius:8,padding:10,marginBottom:12}},
        React.createElement('div',{style:{display:'flex',alignItems:'center',gap:6,marginBottom:8}},
          React.createElement('span',{style:{fontSize:12,fontWeight:600,color:'#e5e7eb'}},c)
        ),
        (s.p>0||s.p_export_global>0)&&React.createElement('div',{style:{marginBottom:6}},
          React.createElement('div',{style:{display:'flex',alignItems:'center',gap:4,fontSize:9,color:'#FBBF24',fontWeight:500,marginBottom:2}},'🏭 生产'),
          React.createElement('div',{style:{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'2px 8px',fontSize:9}},
            s.p>0&&React.createElement(React.Fragment,null,
              React.createElement('span',{style:{color:'#6B7280'}},'全球产量'),
              React.createElement('span',{style:{color:'#FBBF24',textAlign:'right'}},s.p+'%')
            ),
            s.p_export_global>0&&React.createElement(React.Fragment,null,
              React.createElement('span',{style:{color:'#6B7280'}},'出口/全球'),
              React.createElement('span',{style:{color:'#FACC15',textAlign:'right'}},s.p_export_global+'%')
            ),
            s.p_export_ratio>0&&React.createElement(React.Fragment,null,
              React.createElement('span',{style:{color:'#6B7280'}},'出口/产量'),
              React.createElement('span',{style:{color:'#FB923C',textAlign:'right'}},s.p_export_ratio+'%')
            ),
            s.p_export_national>0&&React.createElement(React.Fragment,null,
              React.createElement('span',{style:{color:'#6B7280'}},'占本国总出口'),
              React.createElement('span',{style:{color:'#F87171',textAlign:'right'}},s.p_export_national+'%')
            )
          )
        ),
        (s.d>0||s.d_import_global>0)&&React.createElement('div',null,
          React.createElement('div',{style:{display:'flex',alignItems:'center',gap:4,fontSize:9,color:'#38BDF8',fontWeight:500,marginBottom:2}},'🛒 需求'),
          React.createElement('div',{style:{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'2px 8px',fontSize:9}},
            s.d>0&&React.createElement(React.Fragment,null,
              React.createElement('span',{style:{color:'#6B7280'}},'全球消费'),
              React.createElement('span',{style:{color:'#38BDF8',textAlign:'right'}},s.d+'%')
            ),
            s.d_import_global>0&&React.createElement(React.Fragment,null,
              React.createElement('span',{style:{color:'#6B7280'}},'进口/全球'),
              React.createElement('span',{style:{color:'#7DD3FC',textAlign:'right'}},s.d_import_global+'%')
            )
          )
        )
      );
    })
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App));
</script>
</body></html>''';
  }

  WebViewController get _controller {
    _webCtrl ??= _createController();
    return _webCtrl!;
  }

  WebViewController _createController() {
    final ctrl = WebViewController();
    ctrl.setJavaScriptMode(JavaScriptMode.unrestricted);
    ctrl.addJavaScriptChannel('flutterChannel', onMessageReceived: (msg) {
      final data = jsonDecode(msg.message);
      if (data['type'] == 'back') {
        Navigator.pop(context);
      } else if (data['type'] == 'select') {
        setState(() => _selectedNode = data['node'] as Map<String, dynamic>?);
      }
    });
    ctrl.setNavigationDelegate(NavigationDelegate(
      onPageFinished: (_) {
        if (_nodes.isNotEmpty) _render();
      },
    ));
    ctrl.loadHtmlString(_buildHtml());
    return ctrl;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0B0C10),
      body: SafeArea(
        child: Stack(children: [
          if (_loading)
            const Center(child: CircularProgressIndicator(color: Color(0xFF6B7280))),
          WebViewWidget(controller: _controller),
          // Refresh button
          Positioned(
            top: 16, right: 16,
            child: GestureDetector(
              onTap: _fetchData,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(color: const Color(0xFF141518), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF2A2B30))),
                child: const Icon(Icons.refresh, size: 16, color: Color(0xFF6B7280)),
              ),
            ),
          ),
        ]),
      ),
    );
  }
}
