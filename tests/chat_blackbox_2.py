"""
Black-box test runner for /api/chat endpoint.

Test coverage:
- Binary isobaric T-x-y
- Binary isothermal P-x-y
- Bubble point calculation
- Dew point calculation
- TP Flash calculation
- Azeotrope candidate search
- Phase classification
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

import requests


# =========================
# API地址
# =========================

API_URL = "http://127.0.0.1:8000/api/chat"


# =========================
# 测试请求
# =========================

TEST_CASES = [

    # =====================================================
    # 1. 二元等压 T-x-y
    # =====================================================

    {
        "name": "binary_isobaric_txy",
        "request": {
            "message":
                "计算苯-甲苯在101.325 kPa下的T-x-y相图，"
                "使用Ideal/Raoult模型"
        },
    },


    # =====================================================
    # 2. 二元等温 P-x-y
    # =====================================================

    {
        "name": "binary_isothermal_pxy",
        "request": {
            "message":
                "计算苯-甲苯体系在350 K下的P-x-y相图，"
                "使用Ideal/Raoult模型"
        },
    },


    # =====================================================
    # 3. 泡点计算
    # =====================================================

    {
        "name": "bubble_point",
        "request": {
            "message":
                "计算苯-甲苯混合物泡点，"
                "压力101.325 kPa，"
                "液相组成苯0.5、甲苯0.5"
        },
    },


    # =====================================================
    # 4. 露点计算
    # =====================================================

    {
        "name": "dew_point",
        "request": {
            "message":
                "计算苯-甲苯混合物露点，"
                "压力101.325 kPa，"
                "气相组成苯0.5、甲苯0.5"
        },
    },


    # =====================================================
    # 5. TP Flash
    # =====================================================

    {
        "name": "tp_flash",
        "request": {
            "message":
                "使用Peng-Robinson模型计算"
                "甲烷、乙烷、氮气混合物TP Flash，"
                "温度110 K，压力100 kPa，"
                "摩尔组成为0.965、0.018、0.017"
        },
    },


    # =====================================================
    # 6. 共沸候选搜索
    # =====================================================

    {
        "name": "azeotrope_candidate_search",
        "request": {
            "message":
                "搜索乙醇-水体系在101.325 kPa下的"
                "共沸候选点"
        },
    },


    # =====================================================
    # 7. 基础相态分类
    # =====================================================

    {
        "name": "phase_classification",
        "request": {
            "message":
                "判断甲烷-乙烷混合物在300 K、"
                "5000 kPa条件下的相态"
        },
    },

]


# =========================
# 输出文件
# =========================

OUTPUT_FILE = (
    Path(__file__).parent /
    "thermo_core_chat_test_results.json"
)


# =========================
# 请求函数
# =========================

def send_request(data: dict):

    try:

        response = requests.post(
            API_URL,
            json=data,
            timeout=120,
        )


        try:
            body = response.json()

        except Exception:
            body = response.text


        return {

            "status_code":
                response.status_code,

            "body":
                body,

        }


    except Exception as e:

        return {

            "error":
                str(e)

        }



# =========================
# 主测试流程
# =========================

def main():

    results = []


    print("=" * 70)
    print("Start ThermoEqui-Agent Core Function Testing")
    print("=" * 70)



    for case in TEST_CASES:


        print(
            "\nRunning:",
            case["name"]
        )


        response = send_request(
            case["request"]
        )


        result = {

            "case":
                case["name"],


            "time":
                datetime.now().isoformat(),


            "request":
                case["request"],


            "response":
                response,

        }


        results.append(result)



        print(
            "Status:",
            response.get(
                "status_code",
                "ERROR"
            )
        )



    # 保存测试结果

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:


        json.dump(
            results,
            f,
            ensure_ascii=False,
            indent=4,
        )



    print("\n" + "=" * 70)

    print(
        "Testing Finished"
    )

    print(
        "Result saved:",
        OUTPUT_FILE
    )

    print("=" * 70)



if __name__ == "__main__":

    main()