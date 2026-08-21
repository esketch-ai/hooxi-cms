"""경영 관찰(Executive View) 집계 — OBSERVE_REDESIGN_PLAN OB-R1.

한눈(summary)과 개요(detail)의 데이터 빌더. 전부 read-only.
- 월 그룹핑은 방언 의존 없는 파이썬 집계(행수 수천 이하 — fleet-tables 선례).
- 재무 추이의 매출·매입은 세금계산서(발행일·공급가액) 기준 근사임을 해설에 명시한다
  (회계 원장 매출인식과 산식이 다름 — 추이 관찰 용도).
- 개요(detail)는 각 행에 담당자 이름을 실어 "누구에게 물어볼지"까지 완결한다(3단계 프로세스).
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from models import (
    ActivityHistory,
    Client,
    FleetStatus,
    MarketRate,
    Project,
    ProjectVehicle,
    ReportDelivery,
    Settlement,
    TaxInvoice,
    User,
)
from routers import common
from services import finance_query
from services.market_rate import current_market_rate, trailing_avg_rate

ALLOWED_MONTHS = (6, 12, 24)
OVERDUE_BILLED_DAYS = 30  # 청구 후 미입금 리스크 기준(일)
DETAIL_ROW_CAP = 20


def _month_keys(n: int) -> List[str]:
    """최근 n개월 'YYYY-MM' 오름차순(현재 KST 월 포함)."""
    now = common.now_kst()
    y, m = now.year, now.month
    keys: List[str] = []
    for _ in range(n):
        keys.append("{0:04d}-{1:02d}".format(y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(keys))


def _mk(d) -> Optional[str]:
    """date/datetime → 'YYYY-MM' (None 안전)."""
    if d is None:
        return None
    return "{0:04d}-{1:02d}".format(d.year, d.month)


def _f(v) -> float:
    return float(v) if v is not None else 0.0


def _user_names(db: Session, ids) -> Dict[str, str]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    return {u.user_id: (u.name or u.email) for u in db.query(User).filter(User.user_id.in_(ids)).all()}


# ── summary ────────────────────────────────────────────────────────────
def build_summary(db: Session, months: int) -> dict:
    keys = _month_keys(months)
    keyset = set(keys)
    first_key = keys[0]

    # 재무 추이 — 세금계산서(발행일) 월별 매출/매입 합
    rev = defaultdict(float)
    pur = defaultdict(float)
    for direction, issue_date, supply in (
        db.query(TaxInvoice.direction, TaxInvoice.issue_date, TaxInvoice.supply_amount)
        .filter(TaxInvoice.issue_date.isnot(None))
        .all()
    ):
        k = _mk(issue_date)
        if k not in keyset:
            continue
        if direction == "매출":
            rev[k] += _f(supply)
        elif direction == "매입":
            pur[k] += _f(supply)

    # 정산 입금(완료) 월별 합 + 퍼널 스냅샷
    paid = defaultdict(float)
    settlements = db.query(Settlement).all()
    now = common.now_kst()
    funnel = {
        "CONFIRMED": {"count": 0, "amount": 0.0},
        "BILLED": {"count": 0, "amount": 0.0},
        "COMPLETED": {"count": 0, "amount": 0.0},
    }
    overdue_billed = 0
    receivable_amount = 0.0
    for s in settlements:
        if s.completed_at is not None:
            k = _mk(s.completed_at)
            if k in keyset:
                paid[k] += _f(s.paid_amount if s.paid_amount is not None else s.confirmed_amount)
        st = s.status
        if st in funnel:
            funnel[st]["count"] += 1
            funnel[st]["amount"] += _f(s.confirmed_amount)
        if st == "BILLED":
            receivable_amount += _f(s.confirmed_amount)
            if s.billed_at is not None and (now - s.billed_at).days >= OVERDUE_BILLED_DAYS:
                overdue_billed += 1

    # 예정(퍼널 선두) — 참여(고객사×사업) 조합 중 정산 헤더가 없는 것
    pair_rows = (
        db.query(ProjectVehicle.client_id, ProjectVehicle.project_id, ProjectVehicle.expected_payout)
        .filter(ProjectVehicle.client_id.isnot(None))
        .all()
    )
    settled_pairs = {(s.client_id, s.project_id) for s in settlements}
    sched: Dict[tuple, float] = defaultdict(float)
    for cid, pid, payout in pair_rows:
        if (cid, pid) not in settled_pairs:
            sched[(cid, pid)] += _f(payout)
    funnel_out = [
        {"key": "SCHEDULED", "label": "예정", "count": len(sched), "amount": round(sum(sched.values()), 2)},
        {"key": "CONFIRMED", "label": "확정", "count": funnel["CONFIRMED"]["count"],
         "amount": round(funnel["CONFIRMED"]["amount"], 2)},
        {"key": "BILLED", "label": "청구", "count": funnel["BILLED"]["count"],
         "amount": round(funnel["BILLED"]["amount"], 2)},
        {"key": "COMPLETED", "label": "입금", "count": funnel["COMPLETED"]["count"],
         "amount": round(funnel["COMPLETED"]["amount"], 2)},
    ]

    # 탄소 — 보유/매각·평가·시세
    all_pids = [r[0] for r in db.query(Project.project_id).all()]
    acct = finance_query.project_accounting_batch(db, all_pids)
    held = sum(_f(a.get("held_qty")) for a in acct.values())
    sold = sum(_f(a.get("sold_qty")) for a in acct.values())
    rate = current_market_rate(db)
    rate_f = float(rate) if rate is not None else None
    avg6 = trailing_avg_rate(db)
    avg6_f = float(avg6) if avg6 is not None else None
    valuation = round(held * rate_f, 2) if rate_f is not None else None

    rates = [
        {"date": r.effective_date.isoformat(), "price": _f(r.unit_price)}
        for r in db.query(MarketRate).order_by(MarketRate.effective_date.asc()).all()
    ]

    # 전기 전환 추이 — fleet_status 월별 전기/계
    ev_map: Dict[str, Dict[str, float]] = defaultdict(lambda: {"electric": 0.0, "total": 0.0})
    for period, electric, total in (
        db.query(FleetStatus.period, FleetStatus.electric, FleetStatus.total_count).all()
    ):
        if period:
            ev_map[period]["electric"] += _f(electric)
            ev_map[period]["total"] += _f(total)
    ev_trend = [
        {
            "month": k,
            "electric": int(v["electric"]),
            "total": int(v["total"]),
            "ev_share": round(v["electric"] / v["total"] * 100, 2) if v["total"] else 0.0,
        }
        for k, v in sorted(ev_map.items())
    ]

    # 사업 상태 분포
    dist = defaultdict(int)
    for (st,) in db.query(Project.project_status).all():
        dist[st or "미상"] += 1
    project_dist = [{"status": k, "count": v} for k, v in sorted(dist.items(), key=lambda x: -x[1])]

    # 운영 신호 — 보고서 발송률·긴급 이슈·월별 활동량
    rep = defaultdict(lambda: {"target": 0, "sent": 0})
    for period, status in db.query(ReportDelivery.period, ReportDelivery.status).all():
        if period in keyset and status != "CANCELED":
            rep[period]["target"] += 1
            if status in ("SENT", "CONFIRMED"):
                rep[period]["sent"] += 1
    report_rate = [
        {"month": k, "target": rep[k]["target"], "sent": rep[k]["sent"],
         "rate": round(rep[k]["sent"] / rep[k]["target"] * 100, 1) if rep[k]["target"] else None}
        for k in keys
    ]
    urgent_open = (
        db.query(ActivityHistory)
        .filter(ActivityHistory.activity_type == "ISSUE",
                ActivityHistory.priority == "URGENT",
                ActivityHistory.issue_status != "CLOSED")
        .count()
    )
    act = defaultdict(int)
    first_day = datetime.strptime(first_key + "-01", "%Y-%m-%d")
    for (ad,) in db.query(ActivityHistory.activity_date).filter(
        ActivityHistory.activity_date >= first_day
    ).all():
        k = _mk(ad)
        if k in keyset:
            act[k] += 1
    activity = [{"month": k, "count": act[k]} for k in keys]

    # KPI 스트립 — 최근 월 vs 전월
    cur_k, prev_k = keys[-1], keys[-2] if len(keys) >= 2 else keys[-1]
    total_clients = db.query(Client).filter(Client.contract_status == "ACTIVE").count()
    payout_total = sum(_f(p) for _, _, p in pair_rows)
    kpi = {
        "revenue": {"value": round(rev[cur_k], 2), "prev": round(rev[prev_k], 2),
                    "total12": round(sum(rev.values()), 2)},
        "margin": {"value": round(rev[cur_k] - pur[cur_k], 2),
                   "prev": round(rev[prev_k] - pur[prev_k], 2),
                   "total12": round(sum(rev.values()) - sum(pur.values()), 2)},
        "inventory_valuation": {"value": valuation, "rate": rate_f, "avg6": avg6_f,
                                "held_qty": round(held, 2)},
        "receivable": {"value": round(receivable_amount, 2),
                       "count": funnel["BILLED"]["count"], "overdue30": overdue_billed},
        "expected_payout": {"value": round(payout_total, 2)},
        "clients": {"value": total_clients},
    }

    return {
        "months": keys,
        "kpi": kpi,
        "finance_trend": [
            {"month": k, "revenue": round(rev[k], 2), "purchase": round(pur[k], 2),
             "paid": round(paid[k], 2)}
            for k in keys
        ],
        "funnel": funnel_out,
        "overdue_billed_30": overdue_billed,
        "market_rates": rates,
        "carbon": {"held_qty": round(held, 2), "sold_qty": round(sold, 2),
                   "valuation": valuation, "current_rate": rate_f, "avg6": avg6_f},
        "ev_trend": ev_trend,
        "project_dist": project_dist,
        "report_rate": report_rate,
        "urgent_open": urgent_open,
        "activity": activity,
    }


# ── detail(개요 드로어) — 각 행에 담당자 이름 ─────────────────────────
def _client_names(db: Session, ids) -> Dict[str, str]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    return {c.client_id: c.company_name for c in db.query(Client).filter(Client.client_id.in_(ids)).all()}


def build_detail(db: Session, topic: str, key: Optional[str]) -> dict:
    """개요 드로어 데이터 — 상위 구성 목록(≤20행)+합계+해설. 담당자 이름 포함."""
    if topic in ("revenue", "margin", "month"):
        # 대상 월(기본 최신) 매출/매입 상위 + 그 달 입금 내역
        month = key or _month_keys(1)[0]
        inv = (
            db.query(TaxInvoice)
            .filter(TaxInvoice.issue_date.isnot(None))
            .all()
        )
        sales = [i for i in inv if _mk(i.issue_date) == month and i.direction == "매출"]
        buys = [i for i in inv if _mk(i.issue_date) == month and i.direction == "매입"]
        pids = [i.project_id for i in sales + buys]
        pmap = {p.project_id: p for p in db.query(Project).filter(Project.project_id.in_([x for x in pids if x])).all()}
        unames = _user_names(db, [p.manager_id for p in pmap.values()])

        def _rows(items):
            items = sorted(items, key=lambda x: -_f(x.supply_amount))[:10]
            return [
                {
                    "counterpart": i.counterpart_name or i.invoicee_name or i.invoicer_name,
                    "amount": _f(i.supply_amount),
                    "issue_date": i.issue_date.isoformat() if i.issue_date else None,
                    "project_name": pmap[i.project_id].project_name if i.project_id in pmap else None,
                    "manager": unames.get(pmap[i.project_id].manager_id) if i.project_id in pmap else None,
                }
                for i in items
            ]

        paid_rows = []
        for s in db.query(Settlement).filter(Settlement.completed_at.isnot(None)).all():
            if _mk(s.completed_at) == month:
                paid_rows.append(s)
        cmap = _client_names(db, [s.client_id for s in paid_rows])
        mmap = {c.client_id: c.manager_id for c in db.query(Client).filter(
            Client.client_id.in_(list(cmap.keys()))).all()}
        unames2 = _user_names(db, list(mmap.values()))
        return {
            "topic": "month", "key": month,
            "explain": "{0} 세금계산서(발행일 기준) 매출·매입 상위와 정산 입금 내역입니다. "
                       "금액은 공급가액(부가세 제외).".format(month),
            "sales_total": round(sum(_f(i.supply_amount) for i in sales), 2),
            "purchase_total": round(sum(_f(i.supply_amount) for i in buys), 2),
            "sales_top": _rows(sales),
            "purchase_top": _rows(buys),
            "paid": [
                {"client_name": cmap.get(s.client_id), "amount": _f(s.paid_amount or s.confirmed_amount),
                 "completed_at": s.completed_at.date().isoformat(),
                 "manager": unames2.get(mmap.get(s.client_id))}
                for s in paid_rows[:DETAIL_ROW_CAP]
            ],
        }

    if topic == "receivable":
        rows = (
            db.query(Settlement, Project.project_name)
            .join(Project, Project.project_id == Settlement.project_id)
            .filter(Settlement.status == "BILLED")
            .all()
        )
        now = common.now_kst()
        cmap = _client_names(db, [s.client_id for s, _ in rows])
        cli = {c.client_id: c.manager_id for c in db.query(Client).filter(
            Client.client_id.in_(list(cmap.keys()))).all()}
        unames = _user_names(db, list(cli.values()))
        items = sorted(
            (
                {
                    "client_name": cmap.get(s.client_id), "project_name": pname,
                    "amount": _f(s.confirmed_amount),
                    "billed_at": s.billed_at.date().isoformat() if s.billed_at else None,
                    "days": (now - s.billed_at).days if s.billed_at else None,
                    "manager": unames.get(cli.get(s.client_id)),
                }
                for s, pname in rows
            ),
            key=lambda x: -(x["days"] or 0),
        )[:DETAIL_ROW_CAP]
        return {
            "topic": "receivable", "key": None,
            "explain": "청구(BILLED) 후 아직 입금되지 않은 정산입니다. 경과일 내림차순 — "
                       "{0}일 이상은 리스크로 집계합니다.".format(OVERDUE_BILLED_DAYS),
            "total": round(sum(x["amount"] for x in items), 2),
            "items": items,
        }

    if topic == "funnel":
        stage = (key or "CONFIRMED").upper()
        if stage == "SCHEDULED":
            pair_rows = (
                db.query(ProjectVehicle.client_id, ProjectVehicle.project_id,
                         ProjectVehicle.expected_payout)
                .filter(ProjectVehicle.client_id.isnot(None))
                .all()
            )
            settled = {(s.client_id, s.project_id) for s in db.query(Settlement).all()}
            agg: Dict[tuple, float] = defaultdict(float)
            for cid, pid, payout in pair_rows:
                if (cid, pid) not in settled:
                    agg[(cid, pid)] += _f(payout)
            cmap = _client_names(db, [c for c, _ in agg])
            pmap = {p.project_id: p.project_name for p in db.query(Project).filter(
                Project.project_id.in_([p for _, p in agg])).all()}
            cli = {c.client_id: c.manager_id for c in db.query(Client).filter(
                Client.client_id.in_(list(cmap.keys()))).all()}
            unames = _user_names(db, list(cli.values()))
            items = sorted(
                (
                    {"client_name": cmap.get(cid), "project_name": pmap.get(pid),
                     "amount": round(v, 2), "at": None, "manager": unames.get(cli.get(cid))}
                    for (cid, pid), v in agg.items()
                ),
                key=lambda x: -(x["amount"] or 0),
            )[:DETAIL_ROW_CAP]
            explain = "예상지급액이 산정됐지만 아직 정산 확정 전인 (운수사×사업)입니다."
        else:
            q = db.query(Settlement, Project.project_name).join(
                Project, Project.project_id == Settlement.project_id
            )
            if stage == "COMPLETED":
                rows = q.filter(Settlement.status == "COMPLETED").order_by(
                    Settlement.completed_at.desc()).limit(DETAIL_ROW_CAP).all()
            else:
                rows = q.filter(Settlement.status == stage).all()
            cmap = _client_names(db, [s.client_id for s, _ in rows])
            cli = {c.client_id: c.manager_id for c in db.query(Client).filter(
                Client.client_id.in_(list(cmap.keys()))).all()}
            unames = _user_names(db, list(cli.values()))
            at_field = {"CONFIRMED": "confirmed_at", "BILLED": "billed_at",
                        "COMPLETED": "completed_at"}.get(stage, "confirmed_at")
            items = [
                {"client_name": cmap.get(s.client_id), "project_name": pname,
                 "amount": _f(s.paid_amount if stage == "COMPLETED" and s.paid_amount is not None
                              else s.confirmed_amount),
                 "at": getattr(s, at_field).date().isoformat() if getattr(s, at_field) else None,
                 "manager": unames.get(cli.get(s.client_id))}
                for s, pname in rows[:DETAIL_ROW_CAP]
            ]
            explain = {"CONFIRMED": "확정 후 아직 청구 전인 정산입니다.",
                       "BILLED": "청구 후 입금 대기 중인 정산입니다.",
                       "COMPLETED": "입금 완료된 최근 정산입니다."}[stage]
        return {"topic": "funnel", "key": stage, "explain": explain,
                "total": round(sum(x["amount"] or 0 for x in items), 2), "items": items}

    if topic == "rate":
        rows = (
            db.query(MarketRate)
            .order_by(MarketRate.effective_date.desc())
            .limit(10)
            .all()
        )
        unames = _user_names(db, [r.created_by for r in rows])
        return {
            "topic": "rate", "key": None,
            "explain": "탄소배출권 톤당 시세 등록 이력(최근 10건)입니다. 현재 시세는 "
                       "유효일이 오늘 이하인 최신 값입니다.",
            "items": [
                {"date": r.effective_date.isoformat(), "price": _f(r.unit_price),
                 "note": r.note, "manager": unames.get(r.created_by)}
                for r in rows
            ],
        }

    if topic == "inventory":
        all_pids = [r[0] for r in db.query(Project.project_id).all()]
        acct = finance_query.project_accounting_batch(db, all_pids)
        rate = current_market_rate(db)
        rate_f = float(rate) if rate is not None else None
        pmap = {p.project_id: p for p in db.query(Project).filter(
            Project.project_id.in_(all_pids)).all()}
        unames = _user_names(db, [p.manager_id for p in pmap.values()])
        items = sorted(
            (
                {"project_name": pmap[pid].project_name,
                 "held_qty": round(_f(a.get("held_qty")), 2),
                 "valuation": round(_f(a.get("held_qty")) * rate_f, 2) if rate_f is not None else None,
                 "manager": unames.get(pmap[pid].manager_id)}
                for pid, a in acct.items()
                if pid in pmap and _f(a.get("held_qty")) > 0
            ),
            key=lambda x: -(x["held_qty"] or 0),
        )[:10]
        return {
            "topic": "inventory", "key": None,
            "explain": "사업별 보유(미매각) 수량 × 현재 시세 = 재고평가입니다.",
            "current_rate": rate_f,
            "items": items,
        }

    if topic == "payout":
        rows = (
            db.query(ProjectVehicle.client_id, ProjectVehicle.expected_payout)
            .filter(ProjectVehicle.client_id.isnot(None))
            .all()
        )
        agg: Dict[str, float] = defaultdict(float)
        for cid, p in rows:
            agg[cid] += _f(p)
        cmap = _client_names(db, list(agg.keys()))
        cli = {c.client_id: c.manager_id for c in db.query(Client).filter(
            Client.client_id.in_(list(agg.keys()))).all()}
        unames = _user_names(db, list(cli.values()))
        items = sorted(
            ({"client_name": cmap.get(cid), "amount": round(v, 2),
              "manager": unames.get(cli.get(cid))} for cid, v in agg.items()),
            key=lambda x: -(x["amount"] or 0),
        )[:10]
        return {"topic": "payout", "key": None,
                "explain": "운수사별 예상지급액(참여 차량 합) 상위입니다.",
                "total": round(sum(agg.values()), 2), "items": items}

    if topic == "ev":
        month = key
        if not month:
            row = db.query(FleetStatus.period).order_by(FleetStatus.period.desc()).first()
            month = row[0] if row else None
        agg: Dict[str, Dict[str, float]] = defaultdict(lambda: {"license": 0.0, "electric": 0.0})
        if month:
            for region, lic, ev in (
                db.query(FleetStatus.region, FleetStatus.license_count, FleetStatus.electric)
                .filter(FleetStatus.period == month)
                .all()
            ):
                agg[region or "미상"]["license"] += _f(lic)
                agg[region or "미상"]["electric"] += _f(ev)
        items = sorted(
            (
                {"region": r, "license": int(v["license"]), "electric": int(v["electric"]),
                 "share": round(v["electric"] / v["license"] * 100, 1) if v["license"] else 0.0}
                for r, v in agg.items()
            ),
            key=lambda x: -x["electric"],
        )[:DETAIL_ROW_CAP]
        return {"topic": "ev", "key": month,
                "explain": "{0} 기준 지역(조합)별 면허대수·전기버스입니다.".format(month or "—"),
                "items": items}

    if topic == "project":
        status = key or ""
        q = db.query(Project)
        if status:
            q = q.filter(Project.project_status == status)
        projects = q.order_by(Project.updated_at.desc()).limit(DETAIL_ROW_CAP).all()
        unames = _user_names(db, [p.manager_id for p in projects])
        veh = defaultdict(int)
        for pid, in db.query(ProjectVehicle.project_id).filter(
            ProjectVehicle.project_id.in_([p.project_id for p in projects])
        ).all():
            veh[pid] += 1
        return {
            "topic": "project", "key": status or None,
            "explain": "'{0}' 상태의 사업 목록입니다.".format(status or "전체"),
            "items": [
                {"project_name": p.project_name, "status": p.project_status,
                 "vehicle_count": veh.get(p.project_id, 0),
                 "manager": unames.get(p.manager_id)}
                for p in projects
            ],
        }

    if topic == "signal":
        kind, _, month = (key or "").partition(":")
        if kind == "urgent":
            rows = (
                db.query(ActivityHistory)
                .filter(ActivityHistory.activity_type == "ISSUE",
                        ActivityHistory.priority == "URGENT",
                        ActivityHistory.issue_status != "CLOSED")
                .order_by(ActivityHistory.activity_date.desc())
                .limit(DETAIL_ROW_CAP)
                .all()
            )
            explain = "미처리 긴급 이슈입니다."
        else:  # activity:YYYY-MM / report는 프론트에서 report_rate 표로 대체
            rows = []
            if month:
                start = datetime.strptime(month + "-01", "%Y-%m-%d")
                end = (start + timedelta(days=32)).replace(day=1)
                rows = (
                    db.query(ActivityHistory)
                    .filter(ActivityHistory.activity_date >= start,
                            ActivityHistory.activity_date < end)
                    .order_by(ActivityHistory.activity_date.desc())
                    .limit(DETAIL_ROW_CAP)
                    .all()
                )
            explain = "{0} 활동 기록(최근 {1}건)입니다.".format(month or "—", DETAIL_ROW_CAP)
        cmap = _client_names(db, [h.client_id for h in rows])
        unames = _user_names(db, [h.manager_id for h in rows])
        return {
            "topic": "signal", "key": key,
            "explain": explain,
            "items": [
                {"title": h.title, "client_name": cmap.get(h.client_id),
                 "at": h.activity_date.date().isoformat() if h.activity_date else None,
                 "manager": unames.get(h.manager_id)}
                for h in rows
            ],
        }

    raise ValueError("unknown topic: {0}".format(topic))
