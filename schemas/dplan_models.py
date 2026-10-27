"""依照 D-Plan Schema v4.3 建立的 Pydantic 模型。

設計：每一層 (L1 / L2M / L2 / L3 / L4) 各有兩種模型
  1. ``XxxDraft`` / ``XxxResponse``：給 Gemini 的「輸出限制」。刻意保持精簡 ——
     不讓 LLM 產生 ID、不使用 Dict[str, float] (Gemini 的 response schema
     對 additionalProperties 支援不穩)，改用 [{key, value}] 清單，由程式轉換。
  2. ``Xxx``：最終繳交用、完全貼合 D-Plan.schema v4.3 的嚴格模型
     (extra="forbid"、ID 正規表達式、長度限制)，轉換時順便驗證。

之後新增 L2M / L2 / L3 時，依相同模式在此檔追加即可。
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

SourceId = Annotated[str, StringConstraints(pattern=r"^S[0-9]{1,3}$")]
ObsId = Annotated[str, StringConstraints(pattern=r"^O[0-9]{1,3}$")]
InfId = Annotated[str, StringConstraints(pattern=r"^I[0-9]{1,3}$")]
DecisionId = Annotated[str, StringConstraints(pattern=r"^D[0-9]{1,3}$")]
TickerStr = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}$")]
ActionType = Literal["BUY", "ADD", "TRIM", "SELL_ALL"]


# --------------------------------------------------------------------------- #
# L1：資訊擷取層 observations
# --------------------------------------------------------------------------- #
class ValueItem(BaseModel):
    """單一數值事實 (D-Plan 的 values 只收數字)。"""

    key: str = Field(description="英文 snake_case 指標名稱，如 TAIEX_chg_pct、foreign_net_twd_b")
    value: float = Field(description="純數字 (不可為字串)；單位請寫在 key 內")


class ObservationDraft(BaseModel):
    """Gemini 要產生的單筆事實 (不含 obs_id，由程式依序編號)。"""

    source_ref: List[str] = Field(description="引用的來源 ID 清單，例如 ['S1']，必須來自提供的來源清單")
    topic: str = Field(description="分類標籤，小寫英文 snake_case，如 tw_market、etf_holdings、sentiment")
    statement: str = Field(description="客觀事實陳述 (5~500 字)，只能陳述可核對事實，禁止推論或預測")
    values: List[ValueItem] = Field(description="statement 中出現的關鍵數字，至少 1 筆")


class ObservationsResponse(BaseModel):
    """L1 的 Gemini 回應格式。"""

    observations: List[ObservationDraft] = Field(description="事實清單 (1~100 筆)")


class Observation(BaseModel):
    """D-Plan v4.3 observations 的單筆項目 (最終輸出格式)。"""

    model_config = ConfigDict(extra="forbid")

    obs_id: ObsId
    source_ref: List[SourceId] = Field(min_length=1, max_length=10)
    statement: str = Field(min_length=5, max_length=500)
    values: Dict[str, float] = Field(min_length=1)
    topic: Optional[str] = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,40}$")

    @model_validator(mode="after")
    def _ids_unique(self) -> "Observation":
        if len(set(self.source_ref)) != len(self.source_ref):
            raise ValueError("source_ref 內有重複 ID")
        return self


def drafts_to_observations(
    resp: ObservationsResponse,
    valid_source_ids: Optional[set] = None,
) -> List[Observation]:
    """Gemini 草稿 -> 最終 Observation：依序編號 O1..On、values 轉 dict、檢查引用。"""
    if not 1 <= len(resp.observations) <= 100:
        raise ValueError(f"observations 筆數須為 1~100，實得 {len(resp.observations)}")

    result: List[Observation] = []
    for i, d in enumerate(resp.observations, 1):
        if valid_source_ids is not None:
            bad = [s for s in d.source_ref if s not in valid_source_ids]
            if bad:
                raise ValueError(f"O{i} 引用了不存在的來源 {bad}，可用來源：{sorted(valid_source_ids)}")
        result.append(
            Observation(
                obs_id=f"O{i}",
                source_ref=d.source_ref,
                topic=d.topic or None,
                statement=d.statement,
                values={v.key: v.value for v in d.values},
            )
        )
    return result


# --------------------------------------------------------------------------- #
# L2M：整體市場判斷鏈 market_view
# --------------------------------------------------------------------------- #
RegimeType = Literal["risk_on", "neutral", "risk_off"]
StanceType = Literal["aggressive", "neutral", "defensive"]
NetExposureIntentType = Literal["increase", "hold", "reduce"]


class MarketPostureDraft(BaseModel):
    """Gemini 產生的部位意圖草稿 (posture)。"""

    net_exposure_intent: NetExposureIntentType = Field(
        description="淨曝險意圖：increase (淨買超), hold (|淨買賣| <= 2% NAV), reduce (淨賣超)"
    )
    target_cash_pct_range: List[float] = Field(
        min_length=2,
        max_length=2,
        description="目標現金比例區間 [下限, 上限]，數值介於 0.0 ~ 0.25 且下限 <= 上限",
    )


class MarketPosture(MarketPostureDraft):
    """D-Plan v4.3 嚴格部位意圖模型 (extra='forbid' 且含數值驗證)。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_range(self) -> "MarketPosture":
        low, high = self.target_cash_pct_range
        if not (0.0 <= low <= 0.25 and 0.0 <= high <= 0.25):
            raise ValueError(f"target_cash_pct_range 必須在 0.0 到 0.25 之間，實得: [{low}, {high}]")
        if low > high:
            raise ValueError(f"target_cash_pct_range 下限 ({low}) 不得大於上限 ({high})")
        return self


class MarketViewDraft(BaseModel):
    """Gemini 產生的 market_view 草稿。"""

    basis_refs: List[str] = Field(
        min_length=1,
        max_length=10,
        description="市場級依據 ID 清單 (例如 ['O1'])，必須來自提供的 observations ID",
    )
    logic: str = Field(
        min_length=20,
        max_length=1000,
        description="從依據推導到走向與姿態的過程 (20~1000 字元)",
    )
    regime: RegimeType = Field(
        description="整體市場走向研判：risk_on (進攻), neutral (中性), risk_off (防禦)"
    )
    stance: StanceType = Field(
        description="本日操作姿態：aggressive (積極), neutral (中性), defensive (保守)"
    )
    posture: MarketPostureDraft = Field(
        description="可驗證的部位意圖 (淨曝險意圖與目標現金比例區間)"
    )
    counter_evidence: Optional[str] = Field(
        max_length=500,
        description="與研判相反的市場訊號 (上限 500 字元)；若無反向訊號必須填 null",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="選填：信心度 (0.0 ~ 1.0)",
    )


class MarketViewResponse(BaseModel):
    """給 Gemini 結構化輸出的頂層容器格式 (包含 market_view 鍵)。"""

    market_view: MarketViewDraft = Field(description="L2M 整體市場判斷鏈物件")


class MarketView(BaseModel):
    """D-Plan v4.3 最終嚴格 market_view 模型。"""

    model_config = ConfigDict(extra="forbid")

    basis_refs: List[ObsId] = Field(
        min_length=1,
        max_length=10,
        description="市場級依據 ID 清單 (例如 ['O1'])，每個 ID 必須存在於 observations",
    )
    logic: str = Field(
        min_length=20,
        max_length=1000,
        description="從依據推導到走向與姿態的過程 (20~1000 字元)",
    )
    regime: RegimeType = Field(
        description="整體市場走向研判：risk_on, neutral, risk_off"
    )
    stance: StanceType = Field(
        description="本日操作姿態：aggressive, neutral, defensive"
    )
    posture: MarketPosture = Field(
        description="可驗證的部位意圖 (淨曝險意圖與目標現金比例區間)"
    )
    counter_evidence: Optional[str] = Field(
        max_length=500,
        description="與研判相反的市場訊號 (上限 500 字元)；若無反向訊號必須填 null",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="選填：信心度 (0.0 ~ 1.0)",
    )

    @model_validator(mode="after")
    def _ids_unique(self) -> "MarketView":
        if len(set(self.basis_refs)) != len(self.basis_refs):
            raise ValueError("basis_refs 內有重複 ID")
        return self


def draft_to_market_view(
    draft: MarketViewDraft,
    valid_obs_ids: Optional[set] = None,
) -> MarketView:
    """將 Gemini 產生的草稿轉換並驗證為嚴格的 MarketView 物件。"""
    if valid_obs_ids is not None:
        bad = [b for b in draft.basis_refs if b not in valid_obs_ids]
        if bad:
            raise ValueError(f"basis_refs 引用了不存在的 observation ID {bad}，可用 ID：{sorted(valid_obs_ids)}")

    posture_dict = draft.posture.model_dump()
    return MarketView(
        basis_refs=draft.basis_refs,
        logic=draft.logic,
        regime=draft.regime,
        stance=draft.stance,
        posture=MarketPosture(**posture_dict),
        counter_evidence=draft.counter_evidence,
        confidence=draft.confidence,
    )


# --------------------------------------------------------------------------- #
# L2：個股推論層 inferences
# --------------------------------------------------------------------------- #
class InferenceDraft(BaseModel):
    """Gemini 產生的單筆個股推論草稿 (保持 Schema 輕量以避免 FSM 狀態爆炸)。"""

    inf_id: Optional[str] = Field(
        default=None,
        description="推論 ID，如 I1, I2 (若未填寫程式將自動依序編號)",
    )
    premise_refs: List[str] = Field(
        description="依據之事實 ID 清單 (例如 ['O2', 'O3'])，必須來自提供的 observations ID",
    )
    logic: str = Field(
        description="推導過程：哪些前提數據、為何成立、個股看法與操作意圖",
    )
    conclusion: Optional[str] = Field(
        default=None,
        description="選填：人讀摘要結論",
    )
    counter_evidence: Optional[str] = Field(
        default=None,
        description="與本推論相反的訊號；若無反向訊號必須填 null",
    )
    confidence: Optional[float] = Field(
        default=None,
        description="選填：信心度 (0.0 ~ 1.0)",
    )


class InferencesResponse(BaseModel):
    """給 Gemini 結構化輸出的頂層容器格式 (包含 inferences 陣列)。"""

    inferences: List[InferenceDraft] = Field(
        description="個股推論清單 (建議 20 至 30 筆)",
    )


class Inference(BaseModel):
    """D-Plan v4.3 最終嚴格 inference 模型。"""

    model_config = ConfigDict(extra="forbid")

    inf_id: InfId
    premise_refs: List[ObsId] = Field(min_length=1, max_length=10)
    logic: str = Field(min_length=20, max_length=1000)
    conclusion: Optional[str] = Field(default=None, max_length=300)
    counter_evidence: Optional[str] = Field(max_length=500)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ids_unique(self) -> "Inference":
        if len(set(self.premise_refs)) != len(self.premise_refs):
            raise ValueError("premise_refs 內有重複 ID")
        return self


def drafts_to_inferences(
    resp: InferencesResponse,
    valid_obs_ids: Optional[set] = None,
) -> List[Inference]:
    """將 Gemini 產生的推論草稿轉換並驗證為嚴格的 Inference 清單，並確保 inf_id 編號為 I1..In。"""
    if not 1 <= len(resp.inferences) <= 60:
        raise ValueError(f"inferences 筆數須為 1~60，實得 {len(resp.inferences)}")

    result: List[Inference] = []
    for i, d in enumerate(resp.inferences, 1):
        if valid_obs_ids is not None:
            bad = [p for p in d.premise_refs if p not in valid_obs_ids]
            if bad:
                raise ValueError(f"第 {i} 筆推論引用了不存在的 observation ID {bad}，可用 ID：{sorted(valid_obs_ids)}")

        assigned_id = f"I{i}"
        result.append(
            Inference(
                inf_id=assigned_id,
                premise_refs=d.premise_refs,
                logic=d.logic,
                conclusion=d.conclusion,
                counter_evidence=d.counter_evidence,
                confidence=d.confidence,
            )
        )
    return result


# --------------------------------------------------------------------------- #
# L3：決策層 decisions 與 no_trade_decisions
# --------------------------------------------------------------------------- #
class DecisionDraft(BaseModel):
    """Gemini 產生的單筆異動決策草稿 (保持 Schema 輕量避免 FSM 狀態爆炸)。"""

    decision_id: Optional[str] = Field(
        default=None,
        description="決策 ID，如 D1, D2 (若未填寫程式將自動依序編號)",
    )
    ticker: str = Field(description="台股四位代碼，例如 2330, 2891")
    action: ActionType = Field(description="決策動作: BUY(新建倉), ADD(加碼), TRIM(減碼), SELL_ALL(全數出清)")
    target_weight: float = Field(description="目標權重比率 (0.0 ~ 0.25，如 0.045 代表 4.5%)")
    inference_refs: List[str] = Field(description="引用之推論 ID 清單，例如 ['I1', 'I2']")
    risk_check: Optional[str] = Field(default=None, description="選填：風險檢核人讀自述 (上限 300 字)")
    funding_for: Optional[List[str]] = Field(default=None, description="選填：資金調度宣告 (限 TRIM/SELL_ALL，填指向之買進決策 ID 如 ['D2'])")


class NoTradeDecisionDraft(BaseModel):
    """Gemini 產生的單筆續抱決策草稿。"""

    ticker: str = Field(description="台股四位代碼，例如 2317")
    reason_refs: List[str] = Field(description="續抱理由引用之推論 ID，例如 ['I3']")
    reason: Optional[str] = Field(default=None, description="選填：續抱理由 (上限 300 字)")


class DecisionsResponse(BaseModel):
    """給 Gemini 結構化輸出的頂層容器格式 (包含 decisions 與 no_trade_decisions)。"""

    decisions: List[DecisionDraft] = Field(
        default_factory=list,
        description="當日預計執行的部位買賣調度決策清單 (0~60 筆)",
    )
    no_trade_decisions: List[NoTradeDecisionDraft] = Field(
        default_factory=list,
        description="既有持股中當日續抱不異動者清單 (0~30 筆)",
    )


class Decision(BaseModel):
    """D-Plan v4.3 最終嚴格 decision 模型。"""

    model_config = ConfigDict(extra="forbid")

    decision_id: DecisionId
    ticker: TickerStr
    action: ActionType
    target_weight: float = Field(ge=0.0, le=0.25)
    inference_refs: List[InfId] = Field(min_length=1, max_length=8)
    risk_check: Optional[str] = Field(default=None, max_length=300)
    funding_for: Optional[List[DecisionId]] = Field(default=None, min_length=1, max_length=5)

    @model_validator(mode="after")
    def _validate_decision(self) -> "Decision":
        if len(set(self.inference_refs)) != len(self.inference_refs):
            raise ValueError("inference_refs 內有重複 ID")
        if self.funding_for:
            if len(set(self.funding_for)) != len(self.funding_for):
                raise ValueError("funding_for 內有重複 ID")
            if self.action not in ("TRIM", "SELL_ALL"):
                raise ValueError("只有 TRIM 或 SELL_ALL 動作可填寫 funding_for")
        return self


class NoTradeDecision(BaseModel):
    """D-Plan v4.3 最終嚴格 no_trade_decision 模型。"""

    model_config = ConfigDict(extra="forbid")

    ticker: TickerStr
    reason_refs: List[InfId] = Field(min_length=1, max_length=5)
    reason: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _validate_no_trade(self) -> "NoTradeDecision":
        if len(set(self.reason_refs)) != len(self.reason_refs):
            raise ValueError("reason_refs 內有重複 ID")
        return self


class DecisionsResult(BaseModel):
    """D-Plan v4.3 決策層輸出容器。"""

    decisions: List[Decision] = Field(default_factory=list)
    no_trade_decisions: List[NoTradeDecision] = Field(default_factory=list)


def drafts_to_decisions(
    resp: DecisionsResponse,
    valid_inf_ids: Optional[set] = None,
    prev_holdings_codes: Optional[set] = None,
) -> DecisionsResult:
    """將 Gemini 產生的決策草稿轉換並驗證為嚴格的 DecisionsResult。

    檢核項目：
    1. 自動重編/補齊 decision_id (D1..Dn)。
    2. 檢查 inference_refs 與 reason_refs 引用的推論 ID 是否真實存在。
    3. 昨日持股覆蓋度檢核 (昨日每一檔持股必須恰好出現在 decisions 或 no_trade_decisions 之一)。
    4. 權重檢核：單一個股 <= 10% (台積電 2330 <= 25%)。
    """
    if len(resp.decisions) > 60:
        raise ValueError(f"decisions 筆數最多 60 筆，實得 {len(resp.decisions)}")
    if len(resp.no_trade_decisions) > 30:
        raise ValueError(f"no_trade_decisions 筆數最多 30 筆，實得 {len(resp.no_trade_decisions)}")

    # 1. 驗證並建立 decisions
    final_decisions: List[Decision] = []
    decision_tickers: Set[str] = set()

    for i, d in enumerate(resp.decisions, 1):
        if valid_inf_ids is not None:
            bad = [inf for inf in d.inference_refs if inf not in valid_inf_ids]
            if bad:
                raise ValueError(f"決策 {d.ticker} 引用了不存在的 inference ID {bad}，可用 ID：{sorted(valid_inf_ids)}")

        # 權重檢核
        ticker = d.ticker.strip()
        max_wt = 0.25 if ticker == "2330" else 0.10
        if d.target_weight > max_wt + 1e-4:
            raise ValueError(f"{ticker} 目標權重 {d.target_weight:.3f} 超過法規上限 {max_wt:.2f}")

        assigned_id = f"D{i}"
        final_decisions.append(
            Decision(
                decision_id=assigned_id,
                ticker=ticker,
                action=d.action,
                target_weight=round(d.target_weight, 4),
                inference_refs=d.inference_refs,
                risk_check=d.risk_check,
                funding_for=d.funding_for,
            )
        )
        decision_tickers.add(ticker)

    # 2. 驗證並建立 no_trade_decisions
    final_no_trades: List[NoTradeDecision] = []
    no_trade_tickers: Set[str] = set()

    for j, nt in enumerate(resp.no_trade_decisions, 1):
        ticker = nt.ticker.strip()
        if valid_inf_ids is not None:
            bad = [inf for inf in nt.reason_refs if inf not in valid_inf_ids]
            if bad:
                raise ValueError(f"續抱 {ticker} 引用了不存在的 inference ID {bad}，可用 ID：{sorted(valid_inf_ids)}")

        if ticker in decision_tickers:
            raise ValueError(f"個股 {ticker} 同時出現在 decisions 與 no_trade_decisions，違反互斥原則")
        if ticker in no_trade_tickers:
            raise ValueError(f"個股 {ticker} 在 no_trade_decisions 中重複出現")

        final_no_trades.append(
            NoTradeDecision(
                ticker=ticker,
                reason_refs=nt.reason_refs,
                reason=nt.reason,
            )
        )
        no_trade_tickers.add(ticker)

    # 3. 檢查昨日持股全覆蓋
    if prev_holdings_codes is not None and len(prev_holdings_codes) > 0:
        all_covered = decision_tickers | no_trade_tickers
        missing = prev_holdings_codes - all_covered
        if missing:
            raise ValueError(f"昨日既有持股未獲完全覆蓋！漏掉的標的：{sorted(missing)}")

    return DecisionsResult(
        decisions=final_decisions,
        no_trade_decisions=final_no_trades,
    )


# --------------------------------------------------------------------------- #
# L4：委託層 orders
# --------------------------------------------------------------------------- #
OrderSide = Literal["BUY", "SELL"]


class OrderDraft(BaseModel):
    """Gemini 產生的單筆委託單草稿 (保持 Schema 輕量避免 FSM 狀態爆炸)。"""

    ticker: str = Field(description="台股四位代碼，例如 2330, 2891")
    side: OrderSide = Field(description="買賣方向: BUY (買進) 或 SELL (賣出)")
    shares: int = Field(description="委託股數，必須為 1000 之正整數倍 (整股)")
    decision_ref: str = Field(description="指向之決策 ID，例如 D1, D2")
    derivation_detail: Optional[str] = Field(
        default=None,
        description="選填：人讀推導展開式 (上限 300 字元)",
    )


class OrdersResponse(BaseModel):
    """Gemini 回應的委託層頂層結構 (包含審核覆核資訊)。"""

    orders: List[OrderDraft] = Field(
        default_factory=list,
        description="委託單清單 (0 ~ 60 筆)",
    )
    review_notes: Optional[str] = Field(
        default=None,
        description="選填：經理人針對 Active Share、整股取整、現金水位及風控檢查之審核總結與備註",
    )


class Order(BaseModel):
    """D-Plan v4.3 嚴格委託單規格模型。"""

    model_config = ConfigDict(extra="forbid")

    ticker: TickerStr
    side: OrderSide
    shares: int = Field(ge=1000, description="委託股數，須為 1000 之正整數倍")
    decision_ref: DecisionId
    derivation_detail: Optional[str] = Field(default=None, max_length=300)

    @field_validator("shares")
    @classmethod
    def _validate_round_lot(cls, v: int) -> int:
        if v % 1000 != 0:
            raise ValueError(f"委託股數必須為 1000 的倍數（整股），實得 {v}")
        return v


class OrdersResult(BaseModel):
    """驗證後的委託層結果包裝。"""

    model_config = ConfigDict(extra="forbid")

    orders: List[Order]
    review_notes: Optional[str] = None


def drafts_to_orders(
    resp: OrdersResponse,
    valid_decision_ids: Optional[Set[str]] = None,
    current_holdings: Optional[Dict[str, int]] = None,
) -> OrdersResult:
    """將 Gemini 產生的委託草稿轉換並驗證為嚴格的 Order 清單。"""
    if len(resp.orders) > 60:
        raise ValueError(f"orders 筆數上限為 60 筆，實得 {len(resp.orders)}")

    final_orders: List[Order] = []
    seen_tickers: Set[str] = set()

    for idx, od in enumerate(resp.orders, 1):
        ticker = od.ticker.strip()
        dec_ref = od.decision_ref.strip()

        if valid_decision_ids is not None and dec_ref not in valid_decision_ids:
            raise ValueError(f"第 {idx} 筆委託引用了不存在的 decision ID '{dec_ref}'，可用 ID：{sorted(valid_decision_ids)}")

        # 賣出不可超過持股檢查
        if od.side == "SELL" and current_holdings is not None:
            curr_sh = current_holdings.get(ticker, 0)
            if od.shares > curr_sh:
                raise ValueError(f"委託賣出股數 ({od.shares}) 超過目前庫存持股 ({curr_sh})，標的：{ticker}")

        if ticker in seen_tickers:
            raise ValueError(f"標的 {ticker} 在 orders 中重複出現，每檔當日最多一筆委託")

        final_orders.append(
            Order(
                ticker=ticker,
                side=od.side,
                shares=od.shares,
                decision_ref=dec_ref,
                derivation_detail=od.derivation_detail,
            )
        )
        seen_tickers.add(ticker)

    return OrdersResult(
        orders=final_orders,
        review_notes=resp.review_notes,
    )




