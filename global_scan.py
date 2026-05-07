import asyncio
import json
import subprocess
import sys

COUNTRIES = {
    "美国 (US)": 1,
    "日本 (JP)": 2,
    "香港 (HK)": 13,
    "台湾 (TW)": 14,
    "英国 (UK)": 3,
    "韩国 (KR)": 11,
    "新加坡 (SG)": 16,
    "印度 (IN)": 12,
    "巴西 (BR)": 9,
    "越南 (VN)": 21,
    "泰国 (TH)": 20
}

async def run_global_scan():
    print(f"{'国家':<15} | {'排名':<6} | {'热度':<6} | {'搜索结果':<6}")
    print("-" * 50)
    
    for name, cid in COUNTRIES.items():
        cmd = [sys.executable, "/Users/yishan/.openclaw/workspace/scripts/diandian_rank_check_v2.py", "jujubit", "--country", str(cid), "--json"]
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            
            # Find JSON start
            json_start = stdout.find("--- JSON 报告 ---")
            if json_start != -1:
                json_data = stdout[json_start + len("--- JSON 报告 ---"):].strip()
                report = json.loads(json_data)
                
                rank = report.get("target_rank", "N/A")
                pop = report.get("popularity", 0)
                count = report.get("results_count", 0)
                
                print(f"{name:<15} | {str(rank):<6} | {str(pop):<6} | {str(count):<6}")
            else:
                print(f"{name:<15} | 出错 (未捕获数据)")
                
        except Exception as e:
            print(f"{name:<15} | 脚本错误: {e}")

if __name__ == "__main__":
    asyncio.run(run_global_scan())
