"""种子数据：3 条产业链 — 锂电 / 光伏 / 芯片（8维指标 + 显式上下游）"""

import uuid, sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from db import connect

CHAINS = {
    "lithium_battery": {
        "name": "锂电产业链",
        "nodes": [
            {"name": "锂矿", "type": "原材料", "des": "锂辉石/盐湖卤水提锂", "upstream": [],
             "shares": [
                 {"c":"澳大利亚","p":53,"p_export_global":75,"p_export_ratio":90,"p_export_national":12.0,"d":0,"d_import_global":0,"d_import_ratio":0,"d_import_national":0},
                 {"c":"智利","p":23,"p_export_global":18,"p_export_ratio":60,"p_export_national":8.5,"d":0,"d_import_global":0,"d_import_ratio":0,"d_import_national":0},
                 {"c":"中国","p":15,"p_export_global":3,"p_export_ratio":15,"p_export_national":0.02,"d":60,"d_import_global":70,"d_import_ratio":72,"d_import_national":1.8}],
             "subs": []},
            {"name": "镍矿", "type": "原材料", "des": "红土镍矿/硫化镍矿", "upstream": [],
             "shares": [
                 {"c":"印尼","p":48,"p_export_global":55,"p_export_ratio":70,"p_export_national":6.5,"d":5,"d_import_global":3,"d_import_ratio":2,"d_import_national":0.1},
                 {"c":"菲律宾","p":12,"p_export_global":25,"p_export_ratio":95,"p_export_national":15.0,"d":1,"d_import_global":1,"d_import_ratio":2,"d_import_national":0.05},
                 {"c":"中国","p":4,"p_export_global":2,"p_export_ratio":15,"p_export_national":0.01,"d":58,"d_import_global":65,"d_import_ratio":78,"d_import_national":1.2}],
             "subs": [{"node":"磷酸铁锂","maturity":"已商用","trigger":"镍钴涨价","advantage":"成本低30%","bottleneck":"能量密度偏低"},
                      {"node":"钠离子电池","maturity":"中试","trigger":"锂价持续高位","advantage":"钠资源丰富","bottleneck":"循环寿命待验证"}]},
            {"name": "钴矿", "type": "原材料", "des": "刚果金占全球70%", "upstream": [],
             "shares": [
                 {"c":"刚果金","p":70,"p_export_global":80,"p_export_ratio":92,"p_export_national":55.0,"d":0,"d_import_global":0,"d_import_ratio":0,"d_import_national":0},
                 {"c":"中国","p":1,"p_export_global":1,"p_export_ratio":20,"p_export_national":0.001,"d":50,"d_import_global":68,"d_import_ratio":95,"d_import_national":0.2}],
             "subs": [{"node":"高镍低钴/无钴正极","maturity":"已商用","trigger":"钴价暴涨","advantage":"降本+提升能量密度","bottleneck":"安全性要求更高"}]},
            {"name": "碳酸锂/氢氧化锂", "type": "中间品", "des": "锂盐加工→正极材料前驱体", "upstream": ["锂矿"],
             "shares": [
                 {"c":"中国","p":65,"p_export_global":45,"p_export_ratio":35,"p_export_national":0.5,"d":70,"d_import_global":15,"d_import_ratio":8,"d_import_national":0.1},
                 {"c":"智利","p":20,"p_export_global":35,"p_export_ratio":82,"p_export_national":18.0,"d":5,"d_import_global":3,"d_import_ratio":25,"d_import_national":0.5}],
             "subs": []},
            {"name": "正极材料（三元/铁锂）", "type": "中间品", "des": "三元NCM/NCA vs 磷酸铁锂LFP", "upstream": ["碳酸锂/氢氧化锂", "镍矿", "钴矿"],
             "shares": [
                 {"c":"中国","p":60,"p_export_global":42,"p_export_ratio":28,"p_export_national":0.8,"d":55,"d_import_global":10,"d_import_ratio":5,"d_import_national":0.05},
                 {"c":"韩国","p":15,"p_export_global":25,"p_export_ratio":65,"p_export_national":3.2,"d":0,"d_import_global":18,"d_import_ratio":45,"d_import_national":1.5},
                 {"c":"日本","p":10,"p_export_global":18,"p_export_ratio":72,"p_export_national":1.0,"d":0,"d_import_global":22,"d_import_ratio":60,"d_import_national":0.8}],
             "subs": [{"node":"磷酸锰铁锂LMFP","maturity":"早期商用","trigger":"能量密度提升需求","advantage":"铁锂成本+三元能量密度","bottleneck":"量产一致性"}]},
            {"name": "负极材料（石墨/硅碳）", "type": "中间品", "des": "天然石墨/人造石墨→硅碳负极", "upstream": [],
             "shares": [
                 {"c":"中国","p":85,"p_export_global":75,"p_export_ratio":40,"p_export_national":1.2,"d":60,"d_import_global":12,"d_import_ratio":8,"d_import_national":0.03}],
             "subs": [{"node":"硅碳负极","maturity":"早期商用","trigger":"能量密度瓶颈","advantage":"容量提升10倍","bottleneck":"体积膨胀问题"}]},
            {"name": "隔膜/电解液", "type": "中间品", "des": "湿法/干法隔膜 + LiPF6电解液", "upstream": [],
             "shares": [
                 {"c":"中国","p":55,"p_export_global":32,"p_export_ratio":25,"p_export_national":0.4,"d":50,"d_import_global":15,"d_import_ratio":10,"d_import_national":0.08},
                 {"c":"日本","p":20,"p_export_global":30,"p_export_ratio":65,"p_export_national":0.8,"d":0,"d_import_global":12,"d_import_ratio":25,"d_import_national":0.2},
                 {"c":"韩国","p":15,"p_export_global":22,"p_export_ratio":60,"p_export_national":0.6,"d":0,"d_import_global":18,"d_import_ratio":38,"d_import_national":0.3}],
             "subs": [{"node":"固态电解质","maturity":"研发/中试","trigger":"安全性/能量密度双需求","advantage":"本质安全不燃","bottleneck":"界面阻抗/量产"}]},
            {"name": "电芯/电池包", "type": "零部件", "des": "电芯制造→模组→PACK→BMS", "upstream": ["正极材料（三元/铁锂）", "负极材料（石墨/硅碳）", "隔膜/电解液"],
             "shares": [
                 {"c":"中国","p":70,"p_export_global":48,"p_export_ratio":30,"p_export_national":1.5,"d":55,"d_import_global":8,"d_import_ratio":5,"d_import_national":0.06},
                 {"c":"韩国","p":15,"p_export_global":28,"p_export_ratio":68,"p_export_national":5.5,"d":0,"d_import_global":10,"d_import_ratio":22,"d_import_national":0.4},
                 {"c":"日本","p":8,"p_export_global":14,"p_export_ratio":70,"p_export_national":1.8,"d":0,"d_import_global":12,"d_import_ratio":30,"d_import_national":0.5}],
             "subs": []},
            {"name": "新能源车/储能", "type": "终端", "des": "乘用车/商用车/储能电站", "upstream": ["电芯/电池包"],
             "shares": [
                 {"c":"中国","p":55,"p_export_global":25,"p_export_ratio":18,"p_export_national":3.2,"d":60,"d_import_global":5,"d_import_ratio":3,"d_import_national":0.2},
                 {"c":"欧洲","p":0,"p_export_global":0,"p_export_ratio":0,"p_export_national":0,"d":25,"d_import_global":45,"d_import_ratio":60,"d_import_national":2.5},
                 {"c":"美国","p":0,"p_export_global":0,"p_export_ratio":0,"p_export_national":0,"d":10,"d_import_global":25,"d_import_ratio":75,"d_import_national":1.8}],
             "subs": []},
        ]
    },
    "solar": {
        "name": "光伏产业链",
        "nodes": [
            {"name": "工业硅/硅料", "type": "原材料", "des": "金属硅→多晶硅料（西门子法/颗粒硅）", "upstream": [],
             "shares": [
                 {"c":"中国","p":80,"p_export_global":65,"p_export_ratio":40,"p_export_national":0.3,"d":55,"d_import_global":8,"d_import_ratio":6,"d_import_national":0.02},
                 {"c":"德国","p":5,"p_export_global":12,"p_export_ratio":55,"p_export_national":0.08,"d":0,"d_import_global":15,"d_import_ratio":18,"d_import_national":0.05}],
             "subs": [{"node":"颗粒硅","maturity":"已商用","trigger":"降本压力","advantage":"电耗降70%","bottleneck":"品质一致性"}]},
            {"name": "硅片", "type": "中间品", "des": "拉棒/铸锭→切片", "upstream": ["工业硅/硅料"],
             "shares": [
                 {"c":"中国","p":97,"p_export_global":82,"p_export_ratio":45,"p_export_national":0.5,"d":60,"d_import_global":5,"d_import_ratio":3,"d_import_national":0.01}],
             "subs": []},
            {"name": "光伏银浆", "type": "原材料", "des": "正面银浆/背面银浆→电极", "upstream": [],
             "shares": [
                 {"c":"中国","p":40,"p_export_global":18,"p_export_ratio":22,"p_export_national":0.05,"d":60,"d_import_global":38,"d_import_ratio":28,"d_import_national":0.08},
                 {"c":"日本","p":30,"p_export_global":42,"p_export_ratio":65,"p_export_national":0.2,"d":0,"d_import_global":12,"d_import_ratio":15,"d_import_national":0.04}],
             "subs": [{"node":"银包铜/电镀铜","maturity":"早期商用","trigger":"银价高企","advantage":"降银耗70%","bottleneck":"附着力/可靠性"}]},
            {"name": "电池片", "type": "中间品", "des": "PERC→TOPCon→HJT→钙钛矿叠层", "upstream": ["硅片", "光伏银浆"],
             "shares": [
                 {"c":"中国","p":85,"p_export_global":58,"p_export_ratio":32,"p_export_national":0.6,"d":70,"d_import_global":6,"d_import_ratio":3,"d_import_national":0.02}],
             "subs": [{"node":"HJT异质结","maturity":"早期商用","trigger":"效率天花板","advantage":"效率高/工序少","bottleneck":"设备/银浆成本"},
                      {"node":"钙钛矿叠层","maturity":"研发/中试","trigger":"效率突破需求","advantage":"理论效率40%+","bottleneck":"稳定性/大面积制备"}]},
            {"name": "光伏玻璃", "type": "原材料", "des": "超白压延玻璃→组件封装", "upstream": [],
             "shares": [
                 {"c":"中国","p":90,"p_export_global":68,"p_export_ratio":35,"p_export_national":0.2,"d":80,"d_import_global":3,"d_import_ratio":2,"d_import_national":0.005}],
             "subs": []},
            {"name": "组件", "type": "零部件", "des": "电池片串并联→层压封装→接线盒", "upstream": ["电池片", "光伏玻璃"],
             "shares": [
                 {"c":"中国","p":80,"p_export_global":72,"p_export_ratio":55,"p_export_national":1.8,"d":0,"d_import_global":0,"d_import_ratio":0,"d_import_national":0},
                 {"c":"越南","p":5,"p_export_global":12,"p_export_ratio":92,"p_export_national":8.5,"d":0,"d_import_global":5,"d_import_ratio":15,"d_import_national":0.8}],
             "subs": []},
            {"name": "逆变器", "type": "零部件", "des": "组串式/集中式/微型→直流转交流", "upstream": [],
             "shares": [
                 {"c":"中国","p":65,"p_export_global":55,"p_export_ratio":42,"p_export_national":0.8,"d":50,"d_import_global":10,"d_import_ratio":8,"d_import_national":0.04},
                 {"c":"欧洲","p":15,"p_export_global":18,"p_export_ratio":55,"p_export_national":0.3,"d":0,"d_import_global":25,"d_import_ratio":20,"d_import_national":0.15}],
             "subs": []},
            {"name": "光伏电站/分布式", "type": "终端", "des": "集中式电站/工商业/户用分布式", "upstream": ["组件", "逆变器"],
             "shares": [
                 {"c":"中国","p":0,"p_export_global":0,"p_export_ratio":0,"p_export_national":0,"d":40,"d_import_global":5,"d_import_ratio":2,"d_import_national":0.1},
                 {"c":"欧洲","p":0,"p_export_global":0,"p_export_ratio":0,"p_export_national":0,"d":25,"d_import_global":48,"d_import_ratio":42,"d_import_national":2.0},
                 {"c":"美国","p":0,"p_export_global":0,"p_export_ratio":0,"p_export_national":0,"d":15,"d_import_global":28,"d_import_ratio":35,"d_import_national":1.2}],
             "subs": []},
        ]
    },
    "chip": {
        "name": "芯片产业链",
        "nodes": [
            {"name": "硅晶圆", "type": "原材料", "des": "12英寸/8英寸硅片→芯片衬底", "upstream": [],
             "shares": [
                 {"c":"日本","p":55,"p_export_global":52,"p_export_ratio":45,"p_export_national":1.5,"d":5,"d_import_global":3,"d_import_ratio":22,"d_import_national":0.1},
                 {"c":"台湾","p":20,"p_export_global":18,"p_export_ratio":42,"p_export_national":2.2,"d":10,"d_import_global":8,"d_import_ratio":15,"d_import_national":0.5},
                 {"c":"德国","p":10,"p_export_global":15,"p_export_ratio":68,"p_export_national":0.3,"d":0,"d_import_global":12,"d_import_ratio":28,"d_import_national":0.15}],
             "subs": [{"node":"碳化硅SiC","maturity":"早期商用","trigger":"高压/高频需求","advantage":"耐高压/低损耗","bottleneck":"成本高/缺陷多"}]},
            {"name": "光刻胶/电子化学品", "type": "原材料", "des": "ArF/KrF光刻胶 + 高纯试剂", "upstream": [],
             "shares": [
                 {"c":"日本","p":60,"p_export_global":58,"p_export_ratio":48,"p_export_national":1.2,"d":5,"d_import_global":3,"d_import_ratio":20,"d_import_national":0.08},
                 {"c":"美国","p":15,"p_export_global":18,"p_export_ratio":55,"p_export_national":0.3,"d":0,"d_import_global":8,"d_import_ratio":18,"d_import_national":0.06},
                 {"c":"韩国","p":10,"p_export_global":8,"p_export_ratio":38,"p_export_national":0.2,"d":0,"d_import_global":25,"d_import_ratio":55,"d_import_national":0.8}],
             "subs": []},
            {"name": "半导体设备", "type": "中间品", "des": "光刻机/刻蚀机/薄膜沉积/检测", "upstream": [],
             "shares": [
                 {"c":"美国","p":40,"p_export_global":38,"p_export_ratio":45,"p_export_national":0.8,"d":0,"d_import_global":5,"d_import_ratio":10,"d_import_national":0.05},
                 {"c":"日本","p":25,"p_export_global":28,"p_export_ratio":55,"p_export_national":1.0,"d":0,"d_import_global":8,"d_import_ratio":12,"d_import_national":0.08},
                 {"c":"荷兰","p":18,"p_export_global":20,"p_export_ratio":88,"p_export_national":5.5,"d":0,"d_import_global":3,"d_import_ratio":5,"d_import_national":0.1},
                 {"c":"中国","p":5,"p_export_global":2,"p_export_ratio":18,"p_export_national":0.03,"d":35,"d_import_global":55,"d_import_ratio":68,"d_import_national":2.5}],
             "subs": []},
            {"name": "芯片设计", "type": "中间品", "des": "EDA/IP→逻辑/存储/模拟/射频", "upstream": [],
             "shares": [
                 {"c":"美国","p":55,"p_export_global":58,"p_export_ratio":50,"p_export_national":2.5,"d":30,"d_import_global":10,"d_import_ratio":15,"d_import_national":0.5},
                 {"c":"韩国","p":15,"p_export_global":12,"p_export_ratio":42,"p_export_national":1.8,"d":10,"d_import_global":8,"d_import_ratio":25,"d_import_national":0.6},
                 {"c":"中国","p":10,"p_export_global":3,"p_export_ratio":12,"p_export_national":0.05,"d":40,"d_import_global":45,"d_import_ratio":55,"d_import_national":2.0}],
             "subs": []},
            {"name": "晶圆代工", "type": "中间品", "des": "台积电/三星/中芯国际→芯片制造", "upstream": ["硅晶圆", "光刻胶/电子化学品", "半导体设备", "芯片设计"],
             "shares": [
                 {"c":"台湾","p":63,"p_export_global":68,"p_export_ratio":55,"p_export_national":8.5,"d":5,"d_import_global":3,"d_import_ratio":20,"d_import_national":0.3},
                 {"c":"韩国","p":18,"p_export_global":15,"p_export_ratio":40,"p_export_national":3.2,"d":5,"d_import_global":8,"d_import_ratio":18,"d_import_national":0.4},
                 {"c":"中国","p":7,"p_export_global":3,"p_export_ratio":15,"p_export_national":0.06,"d":60,"d_import_global":62,"d_import_ratio":72,"d_import_national":3.5}],
             "subs": []},
            {"name": "封装测试", "type": "中间品", "des": "先进封装(CoWoS/chiplet)→传统打线", "upstream": ["晶圆代工"],
             "shares": [
                 {"c":"台湾","p":50,"p_export_global":55,"p_export_ratio":58,"p_export_national":6.0,"d":0,"d_import_global":5,"d_import_ratio":8,"d_import_national":0.2},
                 {"c":"中国","p":25,"p_export_global":18,"p_export_ratio":32,"p_export_national":0.4,"d":50,"d_import_global":35,"d_import_ratio":28,"d_import_national":1.0},
                 {"c":"美国","p":10,"p_export_global":12,"p_export_ratio":55,"p_export_national":0.2,"d":0,"d_import_global":28,"d_import_ratio":38,"d_import_national":0.8}],
             "subs": [{"node":"玻璃基板封装","maturity":"研发/早期商用","trigger":"高频/高密度需求","advantage":"低介电损耗/平整度","bottleneck":"易碎/工艺不成熟"}]},
            {"name": "存储芯片(DRAM/NAND)", "type": "零部件", "des": "DRAM/NAND Flash→HBM", "upstream": ["封装测试"],
             "shares": [
                 {"c":"韩国","p":60,"p_export_global":65,"p_export_ratio":58,"p_export_national":8.0,"d":5,"d_import_global":3,"d_import_ratio":20,"d_import_national":0.3},
                 {"c":"美国","p":25,"p_export_global":18,"p_export_ratio":32,"p_export_national":0.6,"d":15,"d_import_global":12,"d_import_ratio":18,"d_import_national":0.4},
                 {"c":"日本","p":10,"p_export_global":12,"p_export_ratio":60,"p_export_national":1.2,"d":0,"d_import_global":10,"d_import_ratio":25,"d_import_national":0.3}],
             "subs": []},
            {"name": "终端应用", "type": "终端", "des": "手机/PC/服务器/AI/汽车", "upstream": ["存储芯片(DRAM/NAND)"],
             "shares": [
                 {"c":"中国","p":0,"p_export_global":0,"p_export_ratio":0,"p_export_national":0,"d":40,"d_import_global":55,"d_import_ratio":65,"d_import_national":5.0},
                 {"c":"美国","p":0,"p_export_global":0,"p_export_ratio":0,"p_export_national":0,"d":25,"d_import_global":22,"d_import_ratio":38,"d_import_national":2.5}],
             "subs": []},
        ]
    }
}

def seed():
    with connect() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM industry_chain_nodes").fetchone()[0]
        if existing > 0:
            print(f"已有 {existing} 条产业链节点，清空后重新播种...")
            conn.execute("DELETE FROM industry_chain_nodes")
            conn.commit()

        for chain_key, chain_data in CHAINS.items():
            # First pass: insert all nodes
            name_to_id = {}
            for i, node in enumerate(chain_data["nodes"]):
                nid = str(uuid.uuid4())
                name_to_id[node["name"]] = nid
                conn.execute("""
                    INSERT INTO industry_chain_nodes (id, chain, name, node_type, description,
                        global_shares, substitutes, upstream_ids, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    nid, chain_data["name"], node["name"], node["type"], node["des"],
                    json.dumps(node.get("shares", []), ensure_ascii=False),
                    json.dumps(node.get("subs", []), ensure_ascii=False),
                    "[]",  # placeholder, will update below
                    i
                ))

            # Second pass: resolve upstream names to IDs
            for node in chain_data["nodes"]:
                upstream_names = node.get("upstream", [])
                upstream_ids = [name_to_id[n] for n in upstream_names]
                nid = name_to_id[node["name"]]
                conn.execute(
                    "UPDATE industry_chain_nodes SET upstream_ids = ? WHERE id = ?",
                    (json.dumps(upstream_ids, ensure_ascii=False), nid)
                )

            print(f"  ✓ {chain_data['name']} — {len(chain_data['nodes'])} 个节点")

        print(f"种子数据录入完成，共 {sum(len(c['nodes']) for c in CHAINS.values())} 个节点（含上游关系）")

if __name__ == '__main__':
    seed()
