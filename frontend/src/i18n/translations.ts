import { SupportedLanguage } from '../types/sirix';

/**
 * Canonical Quant Terms — F00 Section 4.2 & F03 Section 5.1.1
 * These English quantitative labels NEVER change across languages;
 * instead, clicking/hovering the ⓘ badge surfaces a localized explanation.
 */
export type CanonicalQuantTerm =
  | 'Triple-Barrier'
  | 'Chandelier Stop'
  | 'Take-Profit'
  | 'Time Barrier'
  | 'Portfolio Heat'
  | 'Conviction'
  | 'ATR'
  | 'Zero-Override'
  | 'Earnings Blackout'
  | 'Audit Log'
  | 'RUT'
  | 'MID';

export const QUANT_TERM_DEFINITIONS: Record<CanonicalQuantTerm, Record<SupportedLanguage, string>> = {
  'Triple-Barrier': {
    en: 'Institutional 3-sided risk cage surrounding every position: an upper Take-Profit ceiling, a trailing Chandelier Stop floor, and a 14-trading-day vertical Time Barrier.',
    he: 'כלוב ניהול סיכונים מוסדי תלת-ממדי המקיף כל פוזיציה: תקרת יעד רווח (Take-Profit), רצפת סטופ נגרר מבוסס תנודתיות (Chandelier Stop), ומחסום זמן אנכי של 14 ימי מסחר.',
    ar: 'إطار مؤسسي ثلاثي الحواجز لإدارة المخاطر يحيط بكل صفقة: سقف جني الأرباح، ووقف الخسارة المتحرك (Chandelier Stop)، وحاجز زمني رأسي مدته 14 يوم تداول.',
    ru: 'Институциональный трехсторонний контур риска вокруг каждой позиции: верхний потолок фиксации прибыли (Take-Profit), скользящий стоп-уровень (Chandelier Stop) и вертикальный временной барьер в 14 торговых дней.',
  },
  'Chandelier Stop': {
    en: 'Dynamic volatility-indexed trailing floor (Highest High − 3.0 × ATR₁₄) that ratchets upward as price advances and never retreats downward.',
    he: 'רצפת הגנה דינמית הצמודה לתנודתיות (שיא מחיר פחות 3.0 כפול ATR₁₄) הנעה כלפי מעלה בלבד עם עליית המחיר ולעולם אינה נסוגה.',
    ar: 'حد وقف خسارة ديناميكي مرتبط بالتقلبات (أعلى قمة ناقص 3.0 × ATR₁₄) يرتفع تدريجياً مع صعود السعر ولا يتراجع للأسفل أبداً.',
    ru: 'Динамический скользящий уровень защиты с поправкой на волатильность (Максимум − 3.0 × ATR₁₄), который подтягивается только вверх по мере роста цены и никогда не опускается.',
  },
  'Take-Profit': {
    en: 'Upper price target (+3.0R asymmetric reward ceiling) where the autonomous engine harvests gains automatically at EOD.',
    he: 'תקרת מחיר יעד למימוש רווחים (+3.0R יחס סיכוי/סיכון אסימטרי) שבה המנוע האוטונומי מממש רווחים באופן אוטומטי בסוף יום המסחר.',
    ar: 'السعر المستهدف الأعلى لجني الأرباح (+3.0R عائد غير متماثل) حيث يقوم المحرك المستقل بإغلاق الصفقة تلقائياً في نهاية اليوم.',
    ru: 'Верхняя целевая цена фиксации прибыли (асимметричный потолок +3.0R), при достижении которой автономный движок автоматически закрывает сделку по итогам дня.',
  },
  'Time Barrier': {
    en: 'Maximum holding horizon (default 14 trading days). If neither Take-Profit nor Chandelier Stop triggers within this window, the position exits to recycle capital into fresh momentum.',
    he: 'אופק החזקה מרבי (ברירת מחדל: 14 ימי מסחר). אם הפוזיציה לא פגעה ביעד הרווח או בסטופ בתוך חלון זה, היא נסגרת אוטומטית כדי למחזר הון למומנטום חדש.',
    ar: 'أقصى فترة احتفاظ بالصفقة (افتراضياً 14 يوم تداول). إذا لم يتحقق جني الأرباح أو وقف الخسارة خلال هذه النافذة، يتم إغلاق المركز لإعادة تدوير رأس المال.',
    ru: 'Максимальный горизонт удержания позиции (по умолчанию 14 торговых дней). Если за это время не сработали ни Take-Profit, ни Chandelier Stop, позиция закрывается для реинвестирования капитала.',
  },
  'Portfolio Heat': {
    en: 'Aggregate open downside risk across all active positions if every Chandelier Stop were hit simultaneously, expressed as a percentage of Total Equity.',
    he: 'סך הסיכון הפתוח בכל הפוזיציות הפעילות במקרה שבו כל רמות ה-Chandelier Stop יופעלו בו-זמנית, מבוטא כאחוז מסך ההון הכולל.',
    ar: 'إجمالي المخاطر المفتوحة عبر جميع المراكز النشطة في حال تفعيل كافة مستويات وقف الخسارة في آن واحد، معبراً عنه كنسبة مئوية من إجمالي الأسهم.',
    ru: 'Совокупный открытый риск по всем активным позициям при одновременном срабатывании всех защитных уровней Chandelier Stop, выраженный в процентах от общего капитала.',
  },
  Conviction: {
    en: 'Composite 0–100 algorithmic score combining 60-day risk-adjusted momentum, volume surge, and trend smoothness (Choppiness Index filter).',
    he: 'ציון אלגוריתמי משוקלל (0–100) המשלב מומנטום מותאם-סיכון ל-60 יום, זינוק במחזורי המסחר וחלקות מגמה (סינון מדד Choppiness).',
    ar: 'درجة خوارزمية مركبة من 0 إلى 100 تجمع بين الزخم المعدل للمخاطر لمدة 60 يوماً، وطفرة حجم التداول، وسلاسة الاتجاه.',
    ru: 'Композитный алгоритмический балл (0–100), объединяющий 60-дневный импульс с поправкой на риск, всплеск объема и гладкость тренда (фильтр индекса Choppiness).',
  },
  ATR: {
    en: '14-Day Average True Range (Wilder smoothing) measuring daily price volatility in USD to normalize position sizing and stop distances.',
    he: 'טווח תנודה אמיתי ממוצע ל-14 ימים (החלקת Wilder) המודד את התנודתיות היומית בדולרים לצורך נרמול גודל הפוזיציה ומרחקי הסטופ.',
    ar: 'متوسط المدى الحقيقي لمدة 14 يوماً، ويقيس تقلب الأسعار اليومي بالدولار لتوحيد أحجام المراكز ومسافات وقف الخسارة.',
    ru: '14-дневный средний истинный диапазон (сглаживание Уайлдера), измеряющий дневную волатильность цены в USD для нормализации размера позиций и стоп-дистанций.',
  },
  'Zero-Override': {
    en: 'Core SIRIX architectural invariant: 100% autonomous systematic execution. Manual buy, sell, or stop-widening overrides are prohibited to eliminate emotional interference.',
    he: 'עקרון הליבה של SIRIX: ביצוע שיטתי ואוטונומי ב-100%. התערבות ידנית של קנייה, מכירה או הזזת סטופ אסורה בהחלט כדי לנטרל הטיות רגשיות.',
    ar: 'المبدأ الأساسي لنظام SIRIX: تنفيذ آلي ومستقل بنسبة 100%. يُحظر التدخل اليدوي بالبيع أو الشراء أو توسيع وقف الخسارة لمنع القرارات العاطفية.',
    ru: 'Ключевой архитектурный инвариант SIRIX: 100% автономное систематическое исполнение. Ручные покупки, продажи или ослабление стопов запрещены для исключения эмоций.',
  },
  'Earnings Blackout': {
    en: 'Pre-event volatility shield that blocks new entries or exits active holdings prior to quarterly earnings announcements to avoid binary overnight gap risk.',
    he: 'מגן תנודתיות החוסם כניסות חדשות או סוגר החזקות פעילות לפני פרסום דוחות כספיים רבעוניים, למניעת סיכון פערי מחיר (Gaps) בינאריים.',
    ar: 'درع حماية من التقلبات يمنع الدخول الجديد أو يغلق المراكز النشطة قبل إعلانات الأرباح الفصلية لتجنب مخاطر الفجوات السعرية المفاجئة.',
    ru: 'Защитный фильтр волатильности, блокирующий новые входы и закрывающий позиции перед публикацией квартальной отчетности во избежание бинарных ценовых гэпов.',
  },
  'Audit Log': {
    en: 'Immutable historical ledger of every closed swing trade, recording exact entry/exit prices, holding duration, R-Multiple achieved, and the Triple-Barrier exit trigger.',
    he: 'יומן היסטורי בלתי ניתן לשינוי של כל העסקאות שנסגרו, המתעד מחירי כניסה ויציאה, משך החזקה, מכפיל סיכון (R-Multiple) וסיבת היציאה המדויקת.',
    ar: 'سجل تاريخي غير قابل للتعديل لجميع الصفقات المغلقة، يوثق أسعار الدخول والخروج، وفترة الاحتفاظ، ومضاعف العائد للمخاطرة، وسبب الإغلاق.',
    ru: 'Неизменяемый исторический реестр всех закрытых свинг-сделок с фиксацией цен входа/выхода, длительности удержания, R-мультипликатора и триггера закрытия.',
  },
  RUT: {
    en: 'Russell 2000 Small-Cap Index Universe — high-velocity US small-cap equities screened for institutional liquidity and breakout momentum.',
    he: 'מדד Russell 2000 למניות השורה השנייה והשלישית בארה"ב (Small-Cap) — מסונן לנזילות מוסדית ומומנטום פריצה.',
    ar: 'مؤشر راسل 2000 للشركات الأمريكية الصغيرة (Small-Cap) — يتم فحصه للسيولة المؤسسية وزخم الاختراق.',
    ru: 'Индекс компаний малой капитализации США Russell 2000 — высокодинамичные акции, отобранные по критериям институциональной ликвидности и импульса пробоя.',
  },
  MID: {
    en: 'S&P MidCap 400 Index Universe — established US mid-cap growth and industrial leaders exhibiting strong trend persistence.',
    he: 'מדד S&P MidCap 400 למניות בינוניות בארה"ב (Mid-Cap) — חברות צמיחה ותעשייה מבוססות המאופיינות בהמשכיות מגמה חזקה.',
    ar: 'مؤشر S&P MidCap 400 للشركات الأمريكية المتوسطة — شركات نمو وصناعة راسخة تتميز باستمرارية قوية للاتجاه.',
    ru: 'Индекс компаний средней капитализации США S&P MidCap 400 — устойчивые лидеры роста и промышленности с высокой инерцией тренда.',
  },
};

export interface UITranslations {
  nav: {
    portfolio: string;
    search: string;
    preferences: string;
    auditLog: string;
    signOut: string;
  };
  header: {
    autonomousTelemetry: string;
    eodSynced: string;
    offlineCached: string;
    tierBadge: string;
    sandboxMode: string;
  };
  portfolio: {
    totalEquity: string;
    dailyChange: string;
    inceptionReturn: string;
    cashBalance: string;
    investedCapital: string;
    openRiskCap: string;
    auditSeamlessCta: string;
    viewClosedTrades: string;
    activeHoldings: string;
    shares: string;
    entry: string;
    last: string;
    day: string;
    ofDays: string;
    urgencyFresh: string;
    urgencyMaturing: string;
    urgencyCritical: string;
    freeTierBannerTitle: string;
    freeTierBannerSubtitle: string;
    upgradeToProCta: string;
    defensiveModeBadge: string;
    candidatesScanned: string;
    capitalPreserved: string;
    selectPositionPrompt: string;
    noHoldingsTitle: string;
  };
  inspector: {
    title: string;
    closeInspector: string;
    ohlcChartSubtitle: string;
    tripleBarrierCage: string;
    ceilingLabel: string;
    currentPriceLabel: string;
    entryAnchorLabel: string;
    floorLabel: string;
    stopDistanceLabel: string;
    daysRemainingLabel: string;
    nextEarningsLabel: string;
    safeAfterBarrier: string;
    earningsNearWarning: string;
    strategyRationaleLabel: string;
    lockedTelemetryTitle: string;
    lockedTelemetryDesc: string;
    readOnlyNotice: string;
  };
  search: {
    title: string;
    subtitle: string;
    placeholder: string;
    searchButton: string;
    quickPickTitle: string;
    statusHeld: string;
    statusRejected: string;
    viewInPortfolioBtn: string;
    rejectionStageLabel: string;
    gateBreakdownTitle: string;
    gatePassed: string;
    gateFailed: string;
    thresholdRequired: string;
    proGateLockedTitle: string;
    proGateLockedDesc: string;
  };
  audit: {
    title: string;
    subtitle: string;
    winRate: string;
    avgRMultiple: string;
    cumulativeRealized: string;
    totalClosed: string;
    exportCsvBtn: string;
    exportExpertOnly: string;
    freeTruncationNote: string;
    entryToExit: string;
    daysHeld: string;
    shares: string;
  };
  preferences: {
    title: string;
    subtitle: string;
    languageSection: string;
    languageDesc: string;
    themeSection: string;
    themeDesc: string;
    themeObsidian: string;
    themeObsidianDesc: string;
    themeSiriusIce: string;
    themeSiriusIceDesc: string;
    themeSapphire: string;
    themeSapphireDesc: string;
    guardrailsSection: string;
    guardrailsDesc: string;
    maxHeatLabel: string;
    riskPerTradeLabel: string;
    timeBarrierLabel: string;
    earningsBlackoutLabel: string;
    activeUniversesLabel: string;
    immutableEnforced: string;
    saveGuardrailsBtn: string;
    savedSuccess: string;
    expertRequiredBanner: string;
    killSwitchTitle: string;
    killSwitchDesc: string;
    armKillSwitchBtn: string;
    confirmKillSwitchBtn: string;
    cancelBtn: string;
    resumeEngineBtn: string;
    demoTierSwitcherTitle: string;
    demoTierSwitcherDesc: string;
    simulateDefensiveCash: string;
  };
  auth: {
    subtitle: string;
    emailLabel: string;
    passwordLabel: string;
    signInBtn: string;
    sandboxBtn: string;
    zeroOverridePromise: string;
  };
}

export const UI_TRANSLATIONS: Record<SupportedLanguage, UITranslations> = {
  en: {
    nav: {
      portfolio: 'Portfolio',
      search: 'Search',
      preferences: 'Preferences',
      auditLog: 'Audit Log',
      signOut: 'Sign Out',
    },
    header: {
      autonomousTelemetry: 'Autonomous EOD Telemetry',
      eodSynced: 'EOD Snapshot Synced',
      offlineCached: 'Offline Cached Snapshot',
      tierBadge: 'Tier',
      sandboxMode: 'Sandbox Preview',
    },
    portfolio: {
      totalEquity: 'Total Equity',
      dailyChange: 'Daily Change',
      inceptionReturn: 'Inception Return',
      cashBalance: 'Cash Balance',
      investedCapital: 'Invested Capital',
      openRiskCap: 'Cap',
      auditSeamlessCta: 'Closed Trades Ledger & Realized R-Multiples',
      viewClosedTrades: 'Open Audit Log',
      activeHoldings: 'Active Autonomous Holdings',
      shares: 'shs',
      entry: 'Entry',
      last: 'Last',
      day: 'Day',
      ofDays: 'of',
      urgencyFresh: 'FRESH',
      urgencyMaturing: 'MATURING',
      urgencyCritical: 'EXIT SOON',
      freeTierBannerTitle: 'Viewing 2 of 5 Active Autonomous Positions (FREE Tier)',
      freeTierBannerSubtitle: 'Upgrade to PRO or EXPERT to unlock all active holdings, exact Chandelier Stop prices, and Conviction scores.',
      upgradeToProCta: 'Preview PRO Tier',
      defensiveModeBadge: 'SYSTEM STATE: DEFENSIVE CASH PRESERVATION',
      candidatesScanned: 'Candidates Evaluated',
      capitalPreserved: 'Capital Preserved in Cash',
      selectPositionPrompt: 'Select any active holding to inspect its 7-Day OHLC candles and Triple-Barrier risk cage.',
      noHoldingsTitle: '0 Active Positions — 100% Capital in Defensive Cash',
    },
    inspector: {
      title: 'Position Deep-Dive Inspector',
      closeInspector: 'Close',
      ohlcChartSubtitle: '7-Day Daily OHLC Candles with Autonomous Barrier Overlays',
      tripleBarrierCage: 'Active Triple-Barrier Risk Cage',
      ceilingLabel: 'Ceiling • Take-Profit Target',
      currentPriceLabel: 'Current Market Price',
      entryAnchorLabel: 'Execution Entry Anchor',
      floorLabel: 'Floor • Trailing Chandelier Stop',
      stopDistanceLabel: 'Stop Cushion',
      daysRemainingLabel: 'Remaining in Window',
      nextEarningsLabel: 'Next Earnings Event',
      safeAfterBarrier: 'Safe (Outside Window)',
      earningsNearWarning: 'Pre-Earnings Exit Guard Armed',
      strategyRationaleLabel: 'Quantitative Entry Rationale',
      lockedTelemetryTitle: 'Exact Barrier Coordinates Locked on FREE Tier',
      lockedTelemetryDesc: 'Switch to PRO or EXPERT tier to reveal live Take-Profit, Chandelier Stop, ATR cushion, and Conviction telemetry.',
      readOnlyNotice: 'Read-Only Autonomous Telemetry — Manual order execution is disabled by design.',
    },
    search: {
      title: 'Algorithmic Universe Search ("Why Not Stock X?")',
      subtitle: 'Query any Russell 2000 (RUT) or S&P MidCap 400 (MID) ticker to inspect its latest EOD 4-stage screening verdict.',
      placeholder: 'Enter ticker symbol (e.g. NVDA, CELH, DUOL, MSTR, CAVA)...',
      searchButton: 'Inspect Ticker',
      quickPickTitle: 'Sample Screened Tickers:',
      statusHeld: 'CURRENTLY HELD IN PORTFOLIO',
      statusRejected: 'FILTERED OUT AT EOD SCREENING',
      viewInPortfolioBtn: 'Open Live Position Inspector',
      rejectionStageLabel: 'Primary Rejection Gate',
      gateBreakdownTitle: '4-Stage Quantitative Pipeline Breakdown',
      gatePassed: 'PASSED',
      gateFailed: 'REJECTED',
      thresholdRequired: 'Required Threshold',
      proGateLockedTitle: 'Detailed 4-Stage Gate Metrics Locked (FREE Tier)',
      proGateLockedDesc: 'Upgrade to PRO or EXPERT to inspect exact Choppiness Index, ATR, and Momentum Rank gate telemetry.',
    },
    audit: {
      title: 'Closed Trades Audit Log',
      subtitle: 'Immutable ledger of completed swing trades and Triple-Barrier exit triggers.',
      winRate: 'Win Rate',
      avgRMultiple: 'Avg R-Multiple',
      cumulativeRealized: 'Realized P&L',
      totalClosed: 'Closed Trades',
      exportCsvBtn: 'Export Institutional CSV',
      exportExpertOnly: 'CSV Export (EXPERT Tier)',
      freeTruncationNote: 'Showing latest 5 closed trades on FREE tier. Switch to PRO/EXPERT for full ledger history.',
      entryToExit: 'Entry → Exit',
      daysHeld: 'Days Held',
      shares: 'Shares',
    },
    preferences: {
      title: 'Preferences & Autonomous Risk Guardrails',
      subtitle: 'Configure localization, visual telemetry theme, and next-EOD quantitative risk envelopes.',
      languageSection: 'Interface Language & Script Direction',
      languageDesc: 'Switches UI copy and LTR/RTL layout immediately while keeping canonical English quant terms intact.',
      themeSection: 'Visual Telemetry Palette',
      themeDesc: 'Select one of three high-contrast institutional palettes optimized for financial legibility.',
      themeObsidian: 'Obsidian Dark (Default)',
      themeObsidianDesc: 'Deep institutional slate (#090D16) with cyan accents for low-glare dark rooms.',
      themeSiriusIce: 'Sirius Ice Light',
      themeSiriusIceDesc: 'Crisp glacial daylight (#F0F7FF) with high-contrast cobalt and slate typography.',
      themeSapphire: 'Midnight Sapphire',
      themeSapphireDesc: 'Deep naval observatory blue (#0B192C) with sky-blue structural highlights.',
      guardrailsSection: 'Quantitative Risk Guardrails (Next EOD Run)',
      guardrailsDesc: 'Parameters sync to cloud storage and govern the next 21:30 UTC autonomous execution cycle.',
      maxHeatLabel: 'Maximum Portfolio Heat Cap (%)',
      riskPerTradeLabel: 'Risk Allocation Per Trade (% Equity)',
      timeBarrierLabel: 'Vertical Time Barrier Horizon (Trading Days)',
      earningsBlackoutLabel: 'Pre-Earnings Blackout Shield (Days)',
      activeUniversesLabel: 'Monitored Index Universes',
      immutableEnforced: 'IMMUTABLE SYSTEM INVARIANT — ALWAYS ON',
      saveGuardrailsBtn: 'Sync Guardrails to Cloud State',
      savedSuccess: 'Preferences & Guardrails Synchronized',
      expertRequiredBanner: 'Read-Only Preview: Modifying Risk Guardrails and the Emergency Kill-Switch requires EXPERT Tier.',
      killSwitchTitle: 'Emergency Autonomous Kill-Switch',
      killSwitchDesc: 'Halts all new EOD entries and queues orderly liquidation of open holdings at the next market close.',
      armKillSwitchBtn: 'Arm Emergency Kill-Switch',
      confirmKillSwitchBtn: 'Confirm Full EOD Halt & Liquidation',
      cancelBtn: 'Cancel',
      resumeEngineBtn: 'Disarm Kill-Switch & Resume Autonomous Engine',
      demoTierSwitcherTitle: 'Interactive Sandbox Telemetry Controls',
      demoTierSwitcherDesc: 'Test tier-based telemetry gating (FREE / PRO / EXPERT) and Defensive Cash Mode in real time.',
      simulateDefensiveCash: 'Simulate Defensive Cash Mode (0 Holdings)',
    },
    auth: {
      subtitle: 'Autonomous Quantitative Swing-Trading Telemetry Client',
      emailLabel: 'Institutional Email',
      passwordLabel: 'Passphrase',
      signInBtn: 'Authenticate Session',
      sandboxBtn: 'Continue in Interactive Sandbox',
      zeroOverridePromise: 'Strict Zero-Override Architecture • Read-Only Cloud Telemetry',
    },
  },
  he: {
    nav: {
      portfolio: 'תיק השקעות',
      search: 'חיפוש מניה',
      preferences: 'הגדרות וסיכון',
      auditLog: 'יומן עסקאות',
      signOut: 'התנתק',
    },
    header: {
      autonomousTelemetry: 'טלמטריית סוף-יום אוטונומית',
      eodSynced: 'מסונכרן לסוף יום המסחר',
      offlineCached: 'תמונת מצב שמורה (אופליין)',
      tierBadge: 'מסלול',
      sandboxMode: 'סביבת הדגמה',
    },
    portfolio: {
      totalEquity: 'שווי תיק כולל',
      dailyChange: 'שינוי יומי',
      inceptionReturn: 'תשואה מהקמה',
      cashBalance: 'יתרת מזומן',
      investedCapital: 'הון מושקע',
      openRiskCap: 'תקרה',
      auditSeamlessCta: 'יומן עסקאות סגורות ומכפילי רווח ממומשים',
      viewClosedTrades: 'פתח יומן עסקאות',
      activeHoldings: 'פוזיציות אוטונומיות פעילות',
      shares: 'מניות',
      entry: 'כניסה',
      last: 'מחיר אחרון',
      day: 'יום',
      ofDays: 'מתוך',
      urgencyFresh: 'חדש',
      urgencyMaturing: 'מתקדם',
      urgencyCritical: 'קרוב ליציאה',
      freeTierBannerTitle: 'מוצגות 2 מתוך 5 פוזיציות פעילות (מסלול FREE)',
      freeTierBannerSubtitle: 'שדרג למסלול PRO או EXPERT לצפייה בכל ההחזקות, מחירי Chandelier Stop מדויקים וציוני Conviction.',
      upgradeToProCta: 'הדגם מסלול PRO',
      defensiveModeBadge: 'מצב מערכת: שימור הון הגנתי במזומן',
      candidatesScanned: 'מניות שנסרקו',
      capitalPreserved: 'הון מוגן במזומן',
      selectPositionPrompt: 'בחר פוזיציה פעילה לצפייה בגרף נרות של 7 ימים ובכלוב הסיכון התלת-ממדי.',
      noHoldingsTitle: '0 פוזיציות פעילות — 100% מההון שמור במזומן הגנתי',
    },
    inspector: {
      title: 'מפקח פוזיציה לעומק',
      closeInspector: 'סגור',
      ohlcChartSubtitle: 'נרות יומיים (7 ימים) עם שכבות גבולות רווח וסטופ אוטונומיים',
      tripleBarrierCage: 'כלוב גבולות סיכון פעיל',
      ceilingLabel: 'תקרה • יעד מימוש רווח',
      currentPriceLabel: 'מחיר שוק נוכחי',
      entryAnchorLabel: 'מחיר כניסה בעסקה',
      floorLabel: 'רצפה • סטופ נגרר דינמי',
      stopDistanceLabel: 'מרווח ביטחון מסטופ',
      daysRemainingLabel: 'ימים שנותרו בחלון',
      nextEarningsLabel: 'דוח כספי הבא',
      safeAfterBarrier: 'בטוח (מחוץ לחלון)',
      earningsNearWarning: 'הגנת יציאה לפני דוח מופעלת',
      strategyRationaleLabel: 'נימוק כמותי לכניסה לעסקה',
      lockedTelemetryTitle: 'נתוני גבולות מדויקים נעולים במסלול FREE',
      lockedTelemetryDesc: 'עבור למסלול PRO או EXPERT לחשיפת מחירי יעד רווח, Chandelier Stop, מרחק ATR וציון Conviction.',
      readOnlyNotice: 'תצוגת טלמטריה אוטונומית בלבד — ביצוע פקודות ידני מנוטרל במכוון.',
    },
    search: {
      title: 'חיפוש אלגוריתמי ביקום המניות ("למה מניה X לא בתיק?")',
      subtitle: 'חפש כל סימול במדדי Russell 2000 או S&P MidCap 400 לבדיקת תוצאת הסינון האלגוריתמי האחרון.',
      placeholder: 'הזן סימול מניה (למשל NVDA, CELH, DUOL, MSTR, CAVA)...',
      searchButton: 'בדוק סימול',
      quickPickTitle: 'דוגמאות למניות שנסרקו:',
      statusHeld: 'מוחזקת כעת בתיק הפעיל',
      statusRejected: 'נפסלה בסינון סוף-יום אלגוריתמי',
      viewInPortfolioBtn: 'פתח מפקח פוזיציה פעילה',
      rejectionStageLabel: 'שער סינון שפסל את המניה',
      gateBreakdownTitle: 'פירוט 4 שלבי הסינון הכמותיים',
      gatePassed: 'עבר',
      gateFailed: 'נפסל',
      thresholdRequired: 'סף נדרש',
      proGateLockedTitle: 'מדדי שערים מפורטים נעולים (מסלול FREE)',
      proGateLockedDesc: 'שדרג ל-PRO או EXPERT לצפייה בערכי מדד Choppiness, תנודתיות ATR ודירוג המומנטום המדויקים.',
    },
    audit: {
      title: 'יומן ביקורת עסקאות סגורות',
      subtitle: 'תיעוד היסטורי מלא של עסקאות שהושלמו וסיבות היציאה האוטונומיות.',
      winRate: 'אחוז הצלחה',
      avgRMultiple: 'מכפיל R ממוצע',
      cumulativeRealized: 'רווח ממומש מצטבר',
      totalClosed: 'עסקאות שנסגרו',
      exportCsvBtn: 'ייצוא קובץ CSV מוסדי',
      exportExpertOnly: 'ייצוא CSV (מסלול EXPERT)',
      freeTruncationNote: 'מוצגות 5 העסקאות האחרונות במסלול FREE. עבור ל-PRO/EXPERT להיסטוריה המלאה.',
      entryToExit: 'כניסה ← יציאה',
      daysHeld: 'ימי החזקה',
      shares: 'כמות מניות',
    },
    preferences: {
      title: 'העדפות ומעטפת ניהול סיכונים אוטונומית',
      subtitle: 'הגדר שפת ממשק, ערכת נושא חזותית וגבולות סיכון לריצת סוף-היום הבאה.',
      languageSection: 'שפת ממשק וכיוון תצוגה (RTL / LTR)',
      languageDesc: 'מחליף מיידית את שפת הממשק וכיוון הפריסה תוך שמירה על מונחי המקור האנגליים.',
      themeSection: 'ערכת נושא חזותית',
      themeDesc: 'בחר מתוך 3 ערכות צבע מוסדיות בניגודיות גבוהה לקריאות מיטבית של נתונים פיננסיים.',
      themeObsidian: 'Obsidian Dark (ברירת מחדל)',
      themeObsidianDesc: 'לוח צפחה כהה במיוחד (#090D16) עם הדגשות טורקיז לחדרי מסחר.',
      themeSiriusIce: 'Sirius Ice Light (בהיר)',
      themeSiriusIceDesc: 'תצוגת אור-יום קרחית בהירה (#F0F7FF) עם טיפוגרפיה חדה בניגודיות גבוהה.',
      themeSapphire: 'Midnight Sapphire (ספיר עמוק)',
      themeSapphireDesc: 'כחול מצפה-כוכבים עמוק (#0B192C) עם קווי מתאר כחולים בהירים.',
      guardrailsSection: 'גבולות סיכון כמותיים (לריצת סוף-היום הבאה)',
      guardrailsDesc: 'הפרמטרים מסתנכרנים לענן ומנחים את ריצת המנוע האוטונומית הבאה בשעה 21:30 UTC.',
      maxHeatLabel: 'תקרת סיכון תיק מרבית (%)',
      riskPerTradeLabel: 'הקצאת סיכון לעסקה בודדת (% מההון)',
      timeBarrierLabel: 'אופק מחסום זמן אנכי (ימי מסחר)',
      earningsBlackoutLabel: 'מגן איסור מסחר לפני דוחות (ימים)',
      activeUniversesLabel: 'מדדי מניות מנוטרים',
      immutableEnforced: 'חוק מערכת קבוע — פעיל תמיד',
      saveGuardrailsBtn: 'סנכרן גבולות סיכון לענן',
      savedSuccess: 'ההעדפות וגבולות הסיכון סונכרנו בהצלחה',
      expertRequiredBanner: 'תצוגת קריאה בלבד: עריכת גבולות סיכון ומתג החירום זמינה במסלול EXPERT.',
      killSwitchTitle: 'מתג חירום להדממת המנוע (Kill-Switch)',
      killSwitchDesc: 'עוצר כניסות חדשות ומתזמן סגירה מסודרת של כל ההחזקות הפעילות בסוף יום המסחר הבא.',
      armKillSwitchBtn: 'חמש מתג הדממת חירום',
      confirmKillSwitchBtn: 'אשר עצירה מלאה וסגירת פוזיציות בסוף היום',
      cancelBtn: 'ביטול',
      resumeEngineBtn: 'בטל מתג חירום וחדש פעילות אוטונומית',
      demoTierSwitcherTitle: 'בקרי הדגמה אינטראקטיביים (Sandbox)',
      demoTierSwitcherDesc: 'בדוק בזמן אמת את הרשאות המסלולים (FREE / PRO / EXPERT) ואת מצב המזומן ההגנתי.',
      simulateDefensiveCash: 'הדגם מצב מזומן הגנתי (0 החזקות)',
    },
    auth: {
      subtitle: 'מסוף טלמטריה אוטונומי למסחר סווינג כמותי',
      emailLabel: 'דוא"ל מוסדי',
      passwordLabel: 'סיסמה',
      signInBtn: 'התחבר למערכת',
      sandboxBtn: 'המשך במצב הדגמה אינטראקטיבי',
      zeroOverridePromise: 'ארכיטקטורת Zero-Override קפדנית • טלמטריית ענן לקריאה בלבד',
    },
  },
  ar: {
    nav: {
      portfolio: 'المحفظة',
      search: 'البحث',
      preferences: 'الإعدادات والمخاطر',
      auditLog: 'سجل الصفقات',
      signOut: 'تسجيل الخروج',
    },
    header: {
      autonomousTelemetry: 'القياس الكمي المستقل لنهاية اليوم',
      eodSynced: 'تمت مزامنة بيانات نهاية اليوم',
      offlineCached: 'نسخة محفوظة دون اتصال',
      tierBadge: 'الفئة',
      sandboxMode: 'وضع المعاينة التفاعلي',
    },
    portfolio: {
      totalEquity: 'إجمالي قيمة المحفظة',
      dailyChange: 'التغير اليومي',
      inceptionReturn: 'العائد منذ التأسيس',
      cashBalance: 'الرصيد النقدي',
      investedCapital: 'رأس المال المستثمر',
      openRiskCap: 'الحد الأقصى',
      auditSeamlessCta: 'سجل الصفقات المغلقة ومضاعفات العائد المحققة',
      viewClosedTrades: 'فتح سجل التدقيق',
      activeHoldings: 'المراكز النشطة المستقلة',
      shares: 'سهم',
      entry: 'الدخول',
      last: 'السعر الحالي',
      day: 'اليوم',
      ofDays: 'من',
      urgencyFresh: 'جديد',
      urgencyMaturing: 'قيد النضج',
      urgencyCritical: 'إغلاق قريب',
      freeTierBannerTitle: 'عرض 2 من أصل 5 مراكز نشطة (فئة FREE)',
      freeTierBannerSubtitle: 'قم بالترقية إلى فئة PRO أو EXPERT لفتح جميع المراكز وأسعار وقف الخسارة الدقيقة ودرجات القناعة.',
      upgradeToProCta: 'معاينة فئة PRO',
      defensiveModeBadge: 'حالة النظام: الحفاظ الدفاعي على السيولة النقدية',
      candidatesScanned: 'الأسهم التي تم فحصها',
      capitalPreserved: 'رأس المال المحفوظ نقداً',
      selectPositionPrompt: 'اختر أي مركز نشط لفحص شموع 7 أيام وإطار المخاطر ثلاثي الحواجز.',
      noHoldingsTitle: '0 مراكز نشطة — 100% من رأس المال في السيولة الدفاعية',
    },
    inspector: {
      title: 'فاحص المركز التفصيلي',
      closeInspector: 'إغلاق',
      ohlcChartSubtitle: 'شموع يومية لـ 7 أيام مع مستويات الحواجز الآلية',
      tripleBarrierCage: 'إطار الحواجز الثلاثية النشط',
      ceilingLabel: 'السقف • هدف جني الأرباح',
      currentPriceLabel: 'سعر السوق الحالي',
      entryAnchorLabel: 'سعر تنفيذ الدخول',
      floorLabel: 'الأرضية • وقف الخسارة المتحرك',
      stopDistanceLabel: 'هامش الأمان للوقف',
      daysRemainingLabel: 'الأيام المتبقية في النافذة',
      nextEarningsLabel: 'إعلان الأرباح القادم',
      safeAfterBarrier: 'آمن (خارج النافذة)',
      earningsNearWarning: 'حماية الخروج قبل الأرباح مفعلة',
      strategyRationaleLabel: 'المبرر الكمي للدخول',
      lockedTelemetryTitle: 'إحداثيات الحواجز الدقيقة مقفلة في فئة FREE',
      lockedTelemetryDesc: 'انتقل إلى فئة PRO أو EXPERT لإظهار مستويات جني الأرباح ووقف الخسارة وبيانات ATR.',
      readOnlyNotice: 'بيانات قياس للقراءة فقط — تم تعطيل تنفيذ الأوامر اليدوية حسب التصميم.',
    },
    search: {
      title: 'البحث الخوارزمي في المؤشرات ("لماذا لم يتم اختيار السهم X؟")',
      subtitle: 'ابحث عن أي رمز في مؤشر Russell 2000 أو S&P MidCap 400 لفحص نتيجة الفرز الخوارزمي.',
      placeholder: 'أدخل رمز السهم (مثل NVDA, CELH, DUOL, MSTR, CAVA)...',
      searchButton: 'فحص السهم',
      quickPickTitle: 'أمثلة لأسهم تم فحصها:',
      statusHeld: 'محتفظ به حالياً في المحفظة',
      statusRejected: 'تم استبعاده في فرز نهاية اليوم',
      viewInPortfolioBtn: 'فتح فاحص المركز الحي',
      rejectionStageLabel: 'بوابة الاستبعاد الرئيسية',
      gateBreakdownTitle: 'تفصيل مراحل الفرز الكمي الأربع',
      gatePassed: 'اجتاز',
      gateFailed: 'مرفوض',
      thresholdRequired: 'الحد المطلوب',
      proGateLockedTitle: 'تفاصيل البوابات الأربع مقفلة (فئة FREE)',
      proGateLockedDesc: 'قم بالترقية إلى PRO أو EXPERT لفحص قيم مؤشر التذبذب ورتبة الزخم الدقيقة.',
    },
    audit: {
      title: 'سجل تدقيق الصفقات المغلقة',
      subtitle: 'سجل تاريخي ثابت للصفقات المكتملة وأسباب الإغلاق الآلي.',
      winRate: 'نسبة النجاح',
      avgRMultiple: 'متوسط مضاعف R',
      cumulativeRealized: 'الأرباح المحققة',
      totalClosed: 'الصفقات المغلقة',
      exportCsvBtn: 'تصدير ملف CSV مؤسسي',
      exportExpertOnly: 'تصدير CSV (فئة EXPERT)',
      freeTruncationNote: 'يتم عرض أحدث 5 صفقات في فئة FREE. انتقل إلى PRO/EXPERT للسجل الكامل.',
      entryToExit: 'الدخول ← الخروج',
      daysHeld: 'أيام الاحتفاظ',
      shares: 'الأسهم',
    },
    preferences: {
      title: 'التفضيلات وضوابط المخاطر الآلية',
      subtitle: 'تخصيص اللغة، والمظهر البصري، وحدود المخاطر لدورة نهاية اليوم القادمة.',
      languageSection: 'لغة الواجهة واتجاه النص (RTL / LTR)',
      languageDesc: 'يغير لغة الواجهة واتجاه التخطيط فوراً مع الحفاظ على المصطلحات الكمية الإنجليزية.',
      themeSection: 'لوحة الألوان البصرية',
      themeDesc: 'اختر من بين 3 لوحات ألوان مؤسسية عالية التباين لقراءة مالية واضحة.',
      themeObsidian: 'Obsidian Dark (الافتراضي)',
      themeObsidianDesc: 'خلفية داكنة عميقة (#090D16) مع لمسات سماوية لغرف التداول.',
      themeSiriusIce: 'Sirius Ice Light (نهاري)',
      themeSiriusIceDesc: 'مظهر نهاري جليدي ساطع (#F0F7FF) مع تباين عالٍ للقراءة في الإضاءة القوية.',
      themeSapphire: 'Midnight Sapphire (ياقوتي داكن)',
      themeSapphireDesc: 'أزرق فلكي عميق (#0B192C) مع حدود هيكلية زرقاء صافية.',
      guardrailsSection: 'ضوابط المخاطر الكمية (لدورة نهاية اليوم القادمة)',
      guardrailsDesc: 'تتم مزامنة المعلمات مع السحابة لتوجيه دورة التنفيذ المستقلة القادمة الساعة 21:30 UTC.',
      maxHeatLabel: 'الحد الأقصى لحرارة المحفظة (%)',
      riskPerTradeLabel: 'تخصيص المخاطرة لكل صفقة (% من الأسهم)',
      timeBarrierLabel: 'أفق الحاجز الزمني الرأسي (أيام تداول)',
      earningsBlackoutLabel: 'درع الحظر قبل إعلان الأرباح (أيام)',
      activeUniversesLabel: 'المؤشرات الخاضعة للمراقبة',
      immutableEnforced: 'ثابت نظام غير قابل للتعديل — مفعل دائماً',
      saveGuardrailsBtn: 'مزامنة الضوابط مع السحابة',
      savedSuccess: 'تمت مزامنة التفضيلات وضوابط المخاطر',
      expertRequiredBanner: 'معاينة للقراءة فقط: تعديل ضوابط المخاطر ومفتاح الإيقاف الطارئ يتطلب فئة EXPERT.',
      killSwitchTitle: 'مفتاح الإيقاف الطارئ للمحرك (Kill-Switch)',
      killSwitchDesc: 'يوقف جميع عمليات الدخول الجديدة ويجدول تصفية منظمة للمراكز المفتوحة عند الإغلاق القادم.',
      armKillSwitchBtn: 'تجهيز مفتاح الإيقاف الطارئ',
      confirmKillSwitchBtn: 'تأكيد الإيقاف الكامل والتصفية في نهاية اليوم',
      cancelBtn: 'إلغاء',
      resumeEngineBtn: 'إلغاء الإيقاف الطارئ واستئناف المحرك المستقل',
      demoTierSwitcherTitle: 'أدوات تحكم بيئة المعاينة التفاعلية',
      demoTierSwitcherDesc: 'اختبر صلاحيات الفئات (FREE / PRO / EXPERT) ووضع السيولة الدفاعية مباشرة.',
      simulateDefensiveCash: 'محاكاة وضع السيولة الدفاعية (0 مراكز)',
    },
    auth: {
      subtitle: 'عميل القياس الكمي المستقل للتداول المتأرجح',
      emailLabel: 'البريد الإلكتروني المؤسسي',
      passwordLabel: 'كلمة المرور',
      signInBtn: 'توثيق الجلسة',
      sandboxBtn: 'المتابعة في بيئة المعاينة التفاعلية',
      zeroOverridePromise: 'بنية Zero-Override صارمة • قياس سحابي للقراءة فقط',
    },
  },
  ru: {
    nav: {
      portfolio: 'Портфель',
      search: 'Поиск тикера',
      preferences: 'Настройки и риск',
      auditLog: 'Журнал сделок',
      signOut: 'Выйти',
    },
    header: {
      autonomousTelemetry: 'Автономная EOD-телеметрия',
      eodSynced: 'Синхронизировано (EOD)',
      offlineCached: 'Автономный кэш снимка',
      tierBadge: 'Тариф',
      sandboxMode: 'Демо-песочница',
    },
    portfolio: {
      totalEquity: 'Общий капитал',
      dailyChange: 'За день',
      inceptionReturn: 'С начала работы',
      cashBalance: 'Денежный остаток',
      investedCapital: 'Инвестировано',
      openRiskCap: 'Лимит',
      auditSeamlessCta: 'Реестр закрытых сделок и реализованные R-мультипликаторы',
      viewClosedTrades: 'Открыть журнал',
      activeHoldings: 'Активные автономные позиции',
      shares: 'акц.',
      entry: 'Вход',
      last: 'Текущая',
      day: 'День',
      ofDays: 'из',
      urgencyFresh: 'НОВАЯ',
      urgencyMaturing: 'В РАБОТЕ',
      urgencyCritical: 'СКОРО ВЫХОД',
      freeTierBannerTitle: 'Показаны 2 из 5 активных позиций (тариф FREE)',
      freeTierBannerSubtitle: 'Перейдите на PRO или EXPERT, чтобы открыть все позиции, точные уровни Chandelier Stop и баллы Conviction.',
      upgradeToProCta: 'Включить PRO-режим',
      defensiveModeBadge: 'РЕЖИМ СИСТЕМЫ: ЗАЩИТНОЕ СОХРАНЕНИЕ КЭША',
      candidatesScanned: 'Проверено кандидатов',
      capitalPreserved: 'Капитал в защитном кэше',
      selectPositionPrompt: 'Выберите активную позицию для просмотра 7-дневных OHLC-свечей и контура риска Triple-Barrier.',
      noHoldingsTitle: '0 активных позиций — 100% капитала в защитном кэше',
    },
    inspector: {
      title: 'Детальный инспектор позиции',
      closeInspector: 'Закрыть',
      ohlcChartSubtitle: '7-дневные свечи OHLC с наложением автономных барьеров',
      tripleBarrierCage: 'Активный контур риска Triple-Barrier',
      ceilingLabel: 'Потолок • Цель Take-Profit',
      currentPriceLabel: 'Текущая рыночная цена',
      entryAnchorLabel: 'Цена исполнения входа',
      floorLabel: 'Пол • Скользящий Chandelier Stop',
      stopDistanceLabel: 'Запас до стопа',
      daysRemainingLabel: 'Осталось дней в окне',
      nextEarningsLabel: 'Следующий отчет',
      safeAfterBarrier: 'Безопасно (вне окна)',
      earningsNearWarning: 'Защита выхода перед отчетом активна',
      strategyRationaleLabel: 'Количественное обоснование входа',
      lockedTelemetryTitle: 'Точные координаты барьеров скрыты на тарифе FREE',
      lockedTelemetryDesc: 'Переключитесь на тариф PRO или EXPERT для просмотра уровней Take-Profit, Chandelier Stop, ATR и Conviction.',
      readOnlyNotice: 'Автономная телеметрия (только чтение) — ручное выставление заявок отключено архитектурно.',
    },
    search: {
      title: 'Алгоритмический поиск по индексам («Почему нет акции X?»)',
      subtitle: 'Введите любой тикер из Russell 2000 (RUT) или S&P MidCap 400 (MID) для проверки вердикта 4-этапного отбора.',
      placeholder: 'Введите тикер (например: NVDA, CELH, DUOL, MSTR, CAVA)...',
      searchButton: 'Проверить тикер',
      quickPickTitle: 'Примеры проверенных тикеров:',
      statusHeld: 'УДЕРЖИВАЕТСЯ В ПОРТФЕЛЕ',
      statusRejected: 'ОТКЛОНЕНО НА EOD-СКРИНИНГЕ',
      viewInPortfolioBtn: 'Открыть инспектор позиции',
      rejectionStageLabel: 'Причина отклонения',
      gateBreakdownTitle: 'Детализация 4 этапов количественного отбора',
      gatePassed: 'ПРОЙДЕН',
      gateFailed: 'ОТКЛОНЕН',
      thresholdRequired: 'Требуемый порог',
      proGateLockedTitle: 'Детальные метрики 4 этапов скрыты (тариф FREE)',
      proGateLockedDesc: 'Перейдите на PRO или EXPERT для просмотра точных значений Choppiness Index, ATR и ранга импульса.',
    },
    audit: {
      title: 'Аудит-журнал закрытых сделок',
      subtitle: 'Неизменяемый реестр завершенных свинг-сделок и сработавших барьеров выхода.',
      winRate: 'Доля побед',
      avgRMultiple: 'Средний R-мульт.',
      cumulativeRealized: 'Реализованный P&L',
      totalClosed: 'Закрыто сделок',
      exportCsvBtn: 'Экспорт в CSV',
      exportExpertOnly: 'Экспорт CSV (тариф EXPERT)',
      freeTruncationNote: 'На тарифе FREE показаны последние 5 сделок. Переключитесь на PRO/EXPERT для полной истории.',
      entryToExit: 'Вход → Выход',
      daysHeld: 'Дней в сделке',
      shares: 'Акций',
    },
    preferences: {
      title: 'Настройки и автономные лимиты риска',
      subtitle: 'Настройте язык интерфейса, цветовую палитру и параметры риска для следующего EOD-цикла.',
      languageSection: 'Язык интерфейса и направление текста',
      languageDesc: 'Мгновенно переключает язык и направление LTR/RTL, сохраняя канонические английские квант-термины.',
      themeSection: 'Цветовая палитра телеметрии',
      themeDesc: 'Выберите одну из 3 высококонтрастных институциональных тем оформления.',
      themeObsidian: 'Obsidian Dark (По умолчанию)',
      themeObsidianDesc: 'Глубокий обсидиановый фон (#090D16) с циановыми акцентами для темных помещений.',
      themeSiriusIce: 'Sirius Ice Light (Светлая)',
      themeSiriusIceDesc: 'Кристальная дневная тема (#F0F7FF) с высокой контрастностью для яркого освещения.',
      themeSapphire: 'Midnight Sapphire (Сапфировая)',
      themeSapphireDesc: 'Глубокий темно-синий фон (#0B192C) с небесно-голубыми структурными линиями.',
      guardrailsSection: 'Количественные лимиты риска (следующий EOD-цикл)',
      guardrailsDesc: 'Параметры синхронизируются с облаком и применяются в следующем цикле в 21:30 UTC.',
      maxHeatLabel: 'Макс. общий риск портфеля (Portfolio Heat, %)',
      riskPerTradeLabel: 'Риск на одну сделку (% от капитала)',
      timeBarrierLabel: 'Горизонт временного барьера (торговых дней)',
      earningsBlackoutLabel: 'Защитное окно перед отчетом (дней)',
      activeUniversesLabel: 'Активные индексные вселенные',
      immutableEnforced: 'НЕИЗМЕНЯЕМЫЙ ИНВАРИАНТ СИСТЕМЫ — ВСЕГДА ВКЛЮЧЕН',
      saveGuardrailsBtn: 'Синхронизировать лимиты с облаком',
      savedSuccess: 'Настройки и лимиты риска синхронизированы',
      expertRequiredBanner: 'Режим чтения: изменение лимитов риска и аварийный Kill-Switch доступны только на тарифе EXPERT.',
      killSwitchTitle: 'Аварийная остановка движка (Kill-Switch)',
      killSwitchDesc: 'Блокирует новые входы и ставит в очередь плановую ликвидацию всех открытых позиций на закрытии.',
      armKillSwitchBtn: 'Взвести аварийный Kill-Switch',
      confirmKillSwitchBtn: 'Подтвердить полную остановку и закрытие позиций',
      cancelBtn: 'Отмена',
      resumeEngineBtn: 'Отключить Kill-Switch и возобновить работу движка',
      demoTierSwitcherTitle: 'Управление интерактивной песочницей (Sandbox)',
      demoTierSwitcherDesc: 'Протестируйте уровни доступа (FREE / PRO / EXPERT) и защитный режим кэша в реальном времени.',
      simulateDefensiveCash: 'Симулировать защитный режим кэша (0 позиций)',
    },
    auth: {
      subtitle: 'Клиент автономной телеметрии количественного свинг-трейдинга',
      emailLabel: 'Корпоративный Email',
      passwordLabel: 'Пароль',
      signInBtn: 'Войти в терминал',
      sandboxBtn: 'Открыть интерактивную песочницу',
      zeroOverridePromise: 'Строгая архитектура Zero-Override • Облачная телеметрия только для чтения',
    },
  },
};
