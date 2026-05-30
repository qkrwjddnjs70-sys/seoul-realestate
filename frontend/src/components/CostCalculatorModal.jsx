import { useState, useMemo } from 'react'

/* ── 유틸 ── */
const 억 = 10000          // 만원 단위
function fmtMan(m) {
  if (m == null || isNaN(m)) return '-'
  m = Math.round(m)
  if (Math.abs(m) >= 억) {
    const eok = Math.floor(Math.abs(m) / 억)
    const rest = Math.abs(m) % 억
    const sign = m < 0 ? '-' : ''
    return rest > 0 ? `${sign}${eok}억 ${rest.toLocaleString()}만` : `${sign}${eok}억`
  }
  return `${m.toLocaleString()}만`
}

// 규제지역(투기과열) — 강남·서초·송파·용산
const REGULATED = new Set(['11680', '11650', '11710', '11170'])

// 취득세+지방교육세+농특세 (만원 입력, 1주택 기준)
function acquisitionTax(price, areaM2) {
  const eok = price / 억          // 억 단위
  let base                        // 취득세율
  if (eok <= 6) base = 0.01
  else if (eok <= 9) base = (eok * 2 / 3 - 3) / 100   // 6→1%, 9→3% 누진
  else base = 0.03
  const eduTax = base * 0.1       // 지방교육세 = 취득세의 10%
  const farmTax = areaM2 > 85 ? 0.002 : 0   // 농특세 (85㎡ 초과만)
  return price * (base + eduTax + farmTax)
}

// 중개수수료 상한 (서울 2021 개정, 만원 입력)
function brokerFee(price) {
  const eok = price / 억
  let rate
  if (eok < 2) rate = 0.005
  else if (eok < 9) rate = 0.004
  else if (eok < 12) rate = 0.005
  else if (eok < 15) rate = 0.006
  else rate = 0.007
  return Math.min(price * rate, price * rate)   // 상한
}

// 원리금균등 월 상환액 (원금 만원, 연이율 %, 개월)
function monthlyPayment(principal, annualRatePct, months) {
  if (principal <= 0) return 0
  const r = annualRatePct / 100 / 12
  if (r === 0) return principal / months
  return principal * r * Math.pow(1 + r, months) / (Math.pow(1 + r, months) - 1)
}

// 월 상환액 → 최대 원금 (DSR 역산)
function principalFromMonthly(monthly, annualRatePct, months) {
  if (monthly <= 0) return 0
  const r = annualRatePct / 100 / 12
  if (r === 0) return monthly * months
  return monthly * (Math.pow(1 + r, months) - 1) / (r * Math.pow(1 + r, months))
}

const OWNER_OPTIONS = [
  { key: 'first', label: '생애최초', ltv: 0.80, ltvReg: 0.70 },
  { key: 'none', label: '무주택', ltv: 0.70, ltvReg: 0.50 },
  { key: 'one', label: '1주택(처분조건)', ltv: 0.70, ltvReg: 0.50 },
  { key: 'multi', label: '다주택', ltv: 0.60, ltvReg: 0.30 },
]

export default function CostCalculatorModal({ open, onClose, property }) {
  const priceDefault = property?.price || 0
  const [price, setPrice] = useState(priceDefault)        // 만원
  const [income, setIncome] = useState('')                // 연소득 만원
  const [owner, setOwner] = useState('none')
  const [years, setYears] = useState(30)
  const [rate, setRate] = useState(4.0)                   // 실제 금리 %
  const [existingMonthly, setExistingMonthly] = useState('')  // 기존대출 월상환 만원
  const [dsrLimit, setDsrLimit] = useState(40)            // %

  // property 바뀌면 가격 갱신
  useMemo(() => { if (property?.price) setPrice(property.price) }, [property?.id])

  const calc = useMemo(() => {
    const p = Number(price) || 0
    const inc = Number(income) || 0
    const months = years * 12
    const ownerCfg = OWNER_OPTIONS.find(o => o.key === owner)
    const regulated = REGULATED.has(property?.lawd_cd)
    const ltvRate = regulated ? ownerCfg.ltvReg : ownerCfg.ltv

    // 1) LTV 한도
    const ltvCap = p * ltvRate

    // 2) DSR 한도 — 스트레스 금리 +1.5%p 가산하여 산정
    const stressRate = rate + 1.5
    const annualBudget = inc * (dsrLimit / 100)            // 연 원리금 가능액
    const existingAnnual = (Number(existingMonthly) || 0) * 12
    const availAnnual = Math.max(0, annualBudget - existingAnnual)
    const availMonthly = availAnnual / 12
    const dsrCap = inc > 0 ? principalFromMonthly(availMonthly, stressRate, months) : Infinity

    // 3) 실제 대출 = min(LTV, DSR)
    const loan = Math.max(0, Math.min(ltvCap, dsrCap))
    const limitedBy = ltvCap <= dsrCap ? 'LTV' : 'DSR'

    // 4) 월 상환액 (실제 금리로)
    const monthly = monthlyPayment(loan, rate, months)

    // 5) 부대비용
    const acqTax = acquisitionTax(p, property?.area_m2 || 0)
    const broker = brokerFee(p)
    const regCost = p * 0.002 + 50    // 등기·채권·인지·법무 대략 (0.2% + 정액 50만)

    // 6) 필요 현금
    const downPayment = Math.max(0, p - loan)
    const totalCash = downPayment + acqTax + broker + regCost

    return {
      regulated, ltvRate, ltvCap, dsrCap, loan, limitedBy, monthly,
      acqTax, broker, regCost, downPayment, totalCash, stressRate,
    }
  }, [price, income, owner, years, rate, existingMonthly, dsrLimit, property])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="relative flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
           onClick={e => e.stopPropagation()}>
        {/* 헤더 */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <div>
            <h2 className="text-lg font-bold text-gray-900">💰 내 비용 계산하기</h2>
            <p className="text-xs text-gray-400 mt-0.5">{property?.name || '단지'} · {fmtMan(price)} 매수 기준</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* 입력 */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="매매가 (만원)">
              <input type="number" value={price} onChange={e => setPrice(e.target.value)}
                     className="inp" />
            </Field>
            <Field label="연소득 (만원, 세전)">
              <input type="number" value={income} onChange={e => setIncome(e.target.value)}
                     placeholder="예: 7000" className="inp" />
            </Field>
            <Field label="보유 주택">
              <select value={owner} onChange={e => setOwner(e.target.value)} className="inp">
                {OWNER_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
              </select>
            </Field>
            <Field label="대출 기간 (년)">
              <select value={years} onChange={e => setYears(Number(e.target.value))} className="inp">
                {[10, 15, 20, 30, 40].map(y => <option key={y} value={y}>{y}년</option>)}
              </select>
            </Field>
            <Field label="대출 금리 (%)">
              <input type="number" step="0.1" value={rate} onChange={e => setRate(Number(e.target.value))}
                     className="inp" />
            </Field>
            <Field label="기존 대출 월상환 (만원)">
              <input type="number" value={existingMonthly} onChange={e => setExistingMonthly(e.target.value)}
                     placeholder="0" className="inp" />
            </Field>
          </div>

          {/* 결과: 대출 */}
          <div className="rounded-xl border border-blue-200 bg-blue-50/60 p-4">
            <p className="text-xs font-bold text-blue-700 mb-2">🏦 대출 가능 금액</p>
            <div className="flex items-end justify-between">
              <div>
                <p className="text-2xl font-bold text-blue-700">{fmtMan(calc.loan)}</p>
                <p className="text-[11px] text-gray-500 mt-0.5">
                  {calc.limitedBy === 'LTV'
                    ? `LTV ${Math.round(calc.ltvRate*100)}% 한도로 제한`
                    : 'DSR 한도로 제한 (소득 기준)'}
                  {calc.regulated && <span className="ml-1 text-red-500">· 규제지역</span>}
                </p>
              </div>
              <div className="text-right text-xs text-gray-600">
                <p>LTV 한도: {fmtMan(calc.ltvCap)}</p>
                <p>DSR 한도: {calc.dsrCap === Infinity ? '소득 입력 필요' : fmtMan(calc.dsrCap)}</p>
              </div>
            </div>
            <div className="mt-3 pt-3 border-t border-blue-100 flex items-center justify-between">
              <span className="text-xs text-gray-600">월 상환액 ({years}년·{rate}%·원리금균등)</span>
              <span className="text-lg font-bold text-gray-900">{fmtMan(calc.monthly)}<span className="text-xs font-normal text-gray-500">/월</span></span>
            </div>
            {income && (
              <p className="text-[11px] text-gray-500 mt-1">
                DSR 산정 시 스트레스 금리 {calc.stressRate.toFixed(1)}% 적용 (실제 납입은 {rate}% 기준)
              </p>
            )}
          </div>

          {/* 결과: 초기비용 */}
          <div className="rounded-xl border border-gray-200 p-4">
            <p className="text-xs font-bold text-gray-700 mb-2">💵 매수 시 필요한 현금</p>
            <Row label="자기자본 (매매가 − 대출)" value={fmtMan(calc.downPayment)} bold />
            <Row label={`취득세 등 (취득세+지방교육세${(property?.area_m2||0)>85?'+농특세':''})`} value={fmtMan(calc.acqTax)} />
            <Row label="중개수수료 (상한)" value={fmtMan(calc.broker)} />
            <Row label="등기·채권·법무 (추정)" value={fmtMan(calc.regCost)} />
            <div className="mt-2 pt-2 border-t border-gray-200 flex items-center justify-between">
              <span className="text-sm font-bold text-gray-900">총 필요 현금</span>
              <span className="text-xl font-bold text-red-600">{fmtMan(calc.totalCash)}</span>
            </div>
          </div>

          {/* 그 외 고려비용 */}
          <div className="rounded-xl bg-amber-50/60 border border-amber-200 p-4 text-xs text-amber-800 space-y-1">
            <p className="font-bold text-amber-700">📌 추가로 고려할 비용</p>
            <p>• 이사비·입주청소: 100~300만원</p>
            <p>• 인테리어/수리: 구축일수록 ↑ (평당 100~300만원)</p>
            <p>• 재산세·종부세: 보유 중 매년 (공시가 기준)</p>
            <p>• 대출 중도상환수수료: 3년 내 상환 시 0.5~1.2%</p>
            <p>• 장기수선충당금·관리비 예치금</p>
          </div>

          {/* 주의 */}
          <p className="text-[10px] text-gray-400 leading-relaxed">
            ※ 2026년 일반 규제 기준 추정치입니다. 생애최초·신생아·보금자리 등 특례, 은행별 가산금리,
            방공제(소액임차보증금), 신DTI·스트레스DSR 세부 적용에 따라 실제 한도는 달라집니다.
            정확한 한도는 은행 상담을 받으세요.
          </p>
        </div>
      </div>

      <style>{`.inp{width:100%;border:1px solid #d1d5db;border-radius:0.5rem;padding:0.4rem 0.6rem;font-size:0.875rem;outline:none}.inp:focus{border-color:#60a5fa}`}</style>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="text-[11px] text-gray-500 mb-1 block">{label}</span>
      {children}
    </label>
  )
}

function Row({ label, value, bold }) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className={`text-xs ${bold ? 'font-semibold text-gray-800' : 'text-gray-600'}`}>{label}</span>
      <span className={`text-sm ${bold ? 'font-bold text-gray-900' : 'text-gray-700'}`}>{value}</span>
    </div>
  )
}
