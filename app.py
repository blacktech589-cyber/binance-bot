//+------------------------------------------------------------------+
//| ALL FOREX - 12 CANDLE + 10K HIERARCHICAL AI + BREAKOUT GUARD V91           |
//| 12-bar net direction; no consecutive-color requirement            |
//+------------------------------------------------------------------+
#property strict
#property version   "91.00"
#property description "M15 EMA42 slope + FAST MARKET volatility priority + low spread + continuous + AI max-profit"

#include <Trade/Trade.mqh>

CTrade trade;

enum ENUM_FOREX_SIGNAL_MODE
{
   SIGNAL_LIVE_CANDLE=0,
   SIGNAL_DIRECT_900_ONLY=1,
   SIGNAL_DIRECT_900_AI=2,
   SIGNAL_COMBINED_ALL=3,
   SIGNAL_STRATEGY_3000_ONLY=4,
   SIGNAL_AI_DEEP_ONLY=5
};

// Kullanici ayarlari.
input double   InpBaseLot             = 0.01; // 1) Baslangic lotu
bool     InpUseBrokerMinimumLot = false; // 0.01 lot ile basla; broker desteklemiyorsa NormalizeLot min lote yuvarlar // Brokerin SYMBOL_VOLUME_MIN degeriyle basla
input int      InpMaxOpenTrades       = 6;    // 2) Ayni anda islem adedi
bool     InpUseEMA42TrendFilter  = true;
int     InpTrendEMAPeriod       = 42;
double     InpEMA42MinSlopePoints    = 0.0; // 0 = en kucuk yon degisimi bile trend sayilir
int     InpDirectionWindow        = 12;
int     InpDirectionLookback      = 24;
input int      InpMaxSpreadPoints     = 100;  // 3) Maximum Spread (point)
bool     InpLowestSpreadEntry   = true;
bool     InpAutoTakeProfit      = true;
input double   Kari_Al_Para          = 0.09; // 4) KAR AL (hesap para birimi) - hedefe gelince tum sepeti KAPAT
int     InpEntryFirstSeconds   = 10;   // Surekli mod kapaliysa kullanilir
bool     InpContinuousEntryAnyTime = true;
input double   InpEntryDistancePoints = 8.0;  // 5) M15 mum acilisindan giris mesafesi (point)
 // TRUE: M15 mumun her aninda EMA42 yonunde yeni sepet acabilir
bool     InpFastPeakProfitLock  = true;
double     InpPeakGivebackMoney   = 0.01; // Zirveden minimum parasal geri cekilme
double     InpPeakGivebackPercent = 8.0;  // Eski/sabit mod toleransi
bool     InpAdaptiveMaxProfit    = true; // Kâr hizi gucluyse kos, zayiflarsa toleransi daralt
double     InpPeakMinGivebackPct   = 0.25;  // Yavaslama/donus aninda minimum tolerans
double     InpPeakMaxGivebackPct   = 4.0; // Guclu kâr momentumunda maksimum tolerans
input double   InpPeakProfitFloorPct  = 97.0; // 6) Zirve karini koruma tabani (%)
bool     InpAI_MaxProfitExit      = true;
double     InpAI_ExitConfidence     = 0.55;
double     InpAI_MinPeakRetreatPct  = 0.20;
int     InpAI_ProfitEvalMs        = 100;
bool     InpContinuousTrading      = true;
bool     InpExitOnEMA42CandleReversal = true;
double     InpTrendReversalMinRetreatPct = 0.10;
bool     InpUltraPeakLock          = true;
double     InpUltraPeakMinProfit     = 0.09; // bu karin ustunde ultra zirve kilidi aktif
input double   InpUltraPeakRetreatPct = 0.50; // 7) Zirveden izin verilen geri cekilme (%)
input double   InpUltraPeakRetreatMoney = 0.005; // 8) Zirveden parasal geri cekilme
bool     InpImmediateProfitReversalExit = true; // EMA42/mum tersine donerse pozitif kari koru

int     InpStopLossPoints      = 300;

// Haftalik piyasa saatleri - BROKER SUNUCU SAATINE gore.
bool     InpUseWeeklySchedule    = true;
int     InpMondayOpenHour       = 7;
int     InpMondayOpenMinute     = 0;
int     InpFridayCloseHour      = 20;
int     InpFridayCloseMinute    = 0;

// Kapali piyasa korumasi. Eski tick / kapali broker seansi ile ASLA yeni emir gonderme.
bool     InpStrictClosedMarketGuard = true;
int     InpMaxTickAgeSeconds       = 180;
bool     InpRequireBrokerSession    = false;

// Gelismis motor ayarlari kod icinde sabittir ve girdi ekranini kalabaliklastirmaz.
string   InpCommentTag          = "ALL_FOREX_M15_EMA42_DIRECT_MONEY_TP_V91";
long     InpMagic               = 3403901;
bool     InpContinuousOpen      = true;
int      InpMinSpreadPoints     = 0;
int      InpSpreadLookbackSamples = 1200;
int      InpSpreadMinimumSamples  = 1;
int      InpSpreadTolerancePoints = 3;
int      InpCooldownMilliseconds= 0;
ENUM_FOREX_SIGNAL_MODE InpSignalMode = SIGNAL_LIVE_CANDLE;
ENUM_TIMEFRAMES InpTF           = PERIOD_M15;
int      InpDirectionConfirmBars = 8;
int      InpMinimumHoldBars      = 5;
bool     InpMediumVolatilityOnly = false;
bool     InpMediumVolatilityPriority = true;
bool     InpAllowVolatilityFallback  = true;
int      InpVolatilityLookback   = 200;
double   InpMediumVolMinPercentile = 75.0;
double   InpMediumVolMaxPercentile = 97.0;
double   InpMediumVolMinRatio    = 1.35;
double   InpMediumVolMaxRatio    = 2.60;
double   InpMinSignalStrength   = 0.25;
bool     InpUseDirect900        = true;
double   InpDirectWeight        = 0.65;
int      InpDirectMinVoteLead   = 5;
bool     InpUseAdvanced100      = true;
double   InpAdvanced100Weight   = 0.30;
bool     InpCandleFallback      = true;
bool     InpUse3000Strategies   = true;
double   InpStrategyWeight      = 0.35;
bool     InpRequireAgreement    = false;
double   InpMinAgreement        = 0.52;

bool     AI_Derin_Ogrenme       = true;
double   AI_Agirlik             = 0.45;
double   AI_Min_Guven           = 0.55;
double   AI_Ogrenme_Hizi        = 0.0009;
double   AI_Agirlik_Curumesi    = 0.00001;
bool     AI_Rejim_Agirliklama   = true;
bool     AI_Basari_Agirliklama  = true;
bool     AI_Odakli_Zor_Ornek    = true;
bool     AI_Guven_Kalibrasyonu  = true;
double   AI_Dinamik_Min_Agirlik = 0.15;
double   AI_Dinamik_Max_Agirlik = 0.65;
int      AI_Ag_Sayisi           = 10000;
double   AI_Mikro_Agirlik       = 0.38;
bool     AI_Ag_Kalici_Ogrenme   = true;
int      AI_Ag_Kayit_Araligi    = 25;

int      AI_Gecmis_Min_Mum      = 2000;
long     AI_Gecmis_Hedef_Mum    = 60000000;
int      AI_Gecmis_Parti        = 20000;
long     AI_Gecmis_Hedef_Hiz     = 800000;   // Hedef throughput; gercek hiz donanima/terminal verisine baglidir.
bool     AI_Gecmis_Tekrarli_Ogrenme = true; // Mevcut gecmisi epoch olarak tekrar tekrar tara.
int      AI_Gecmis_Derin_Egitim_Araligi = 2048; // Her N tarih orneginde 10K ensemble backprop.
int      AI_Gecmis_Kayit_Araligi_MS = 5000;
bool     AI_Kalici_Hafiza       = true;
double   AI_Hafiza_Agirlik      = 0.30;
int      AI_Hafiza_Min_Ornek    = 5;
bool     AI_Gecmis_Hazirlik_Bekle = false;

// V65 HIERARCHICAL AI: rejim uzmanlari, drift farkindaligi ve hiyerarsik zaman birlestirme.
bool     AI_Coklu_Ufuk_Ogrenme  = true;
double   AI_Etiket_Yumusatma    = 0.035;
double   AI_Gradient_Kirpma     = 1.10;
double   AI_Min_Hareket_ATR     = 0.03;
bool     AI_Dinamik_Birlestirme = true;
bool     AI_Zamansal_Dikkat      = true;
bool     AI_Rejim_Uzlasma        = true;
double   AI_Belirsizlik_Cezasi   = 1.20;

// V65: 384 M1 zaman ufku + 12 rejim uzmani + drift farkindaligi + meta fusion.
const int AI_MULTI_HORIZONS      = 384;
const int AI_REGIME_EXPERTS      = 12;
bool     AI_Adaptif_Ogrenme      = true;
bool     AI_Cift_Hiz_Basari      = true;
bool     AI_Meta_Birlestirme     = true;
bool     AI_Rejim_Istikrar       = true;
bool     AI_Hiyerarsik_Rejim     = true;
bool     AI_Drift_Farkindalik    = true;
bool     AI_Entropi_Kalibrasyon  = true;
double   AI_Meta_Agirlik         = 0.30;
double   AI_Drift_Cezasi         = 0.32;
double   AI_Uzman_Agirlik        = 0.26;

// Kirilma varsa yeni pozisyon acma.
bool     InpUseBreakoutGuard       = true;
int      InpBreakoutLookback       = 20;
double   InpBreakoutChannelATR     = 0.05;
double   InpBreakoutRangeATR       = 2.30;
double   InpBreakoutVelocityATR    = 3.20;

int      InpFastMA              = 9;
int      InpSlowMA              = 21;
int      InpATRPeriod           = 14;
int      InpRSIPeriod           = 14;
bool     InpUseRSI              = true;
double   InpRSIMinEntry         = 50.0;
double   InpRSIMaxEntry         = 70.0;
double   InpRSIBuyLevel         = 52.0;
double   InpRSISellLevel        = 48.0;
double   InpRSIWeight           = 0.40;
bool     InpUseBollinger        = true;
int      InpBollingerPeriod     = 20;
double   InpBollingerDeviation  = 2.0;
double   InpBollingerWeight     = 0.60;
bool     InpRequireIndicatorAgreement = false;

bool     InpUseDynamicTP        = false;
double   InpTPMultiplier        = 2.5;
int      InpDeviationPoints     = 200;
bool     InpMaxDrawdownGuard    = true;
double   InpMaxDrawdownPct      = 8.0;
bool     InpSingleDirection     = true;
bool     InpCloseOppositeProfit = true;
double   InpMinimumCloseProfit  = 0.01;

const int STRATEGY_FAMILIES=30;
const int STRATEGY_HORIZONS=20;
const int STRATEGY_VARIANTS=5;
const int STRATEGY_COUNT=3000;
const int DIRECT_CATEGORIES=18;
const int DIRECT_RULES_PER_CATEGORY=50;
const int DIRECT_STRATEGY_COUNT=900;
const int ADVANCED_STRATEGY_COUNT=100;
const int AI_INPUTS=28;
const int AI_HIDDEN_1=48;
const int AI_HIDDEN_2=24;
const int AI_MODELS=5;
const int AI_MICRO_INPUTS=8;
const int AI_MICRO_MINIMUM=10000;
const int AI_MICRO_CAPACITY=12000;
const int AI_MEMORY_BUCKETS=65536;

int hFastMA=INVALID_HANDLE;
int hTrendEMA=INVALID_HANDLE;
int hSlowMA=INVALID_HANDLE;
int hATR=INVALID_HANDLE;
int hRSI=INVALID_HANDLE;
int hBands=INVALID_HANDLE;

double strategyVotes[];
double directStrategyVotes[];
double advancedStrategyVotes[];
double aiW1[5][48][28];
double aiB1[5][48];
double aiW2[5][24][48];
double aiB2[5][24];
double aiW3[5][24];
double aiB3[5];
double aiModelAccuracy[5];
double aiModelFastQuality[5];
double lastAIModelProbability[5];
double aiMicroW[12000][8];
double aiMicroB[12000];
double aiMicroAccuracy[12000];
double aiMicroFastQuality[12000];
double aiMemoryCount[65536];
double aiMemoryUpSum[65536];
double aiPendingInput[28];
bool aiHasPendingSample=false;
datetime aiLastSampleBar=0;
int aiTrainingCount=0;
double lastAIProbability=0.50;
double lastAIScore=0.0;
double lastAIConfidence=0.0;
double lastAILoss=0.0;
double lastAIDisagreement=0.0;
double lastAIConsensus=0.50;
double lastAISmartWeight=0.0;
double lastAIAverageAccuracy=0.50;
double lastMicroProbability=0.50;
double lastMicroDisagreement=0.0;
int lastMicroBuyVotes=0;
int lastMicroSellVotes=0;
int lastMicroNeutralVotes=0;
double lastAIDeepReliability=0.50;
double lastAIMicroReliability=0.50;
double lastAIFusionQuality=0.50;
double lastAISoftTarget=0.50;
double lastMultiHorizonScore=0.0;
double lastMultiHorizonAgreement=0.0;
double lastAITemporalPrior=0.50;
double lastAIRegimeConsensus=0.50;
double lastAIUncertainty=0.0;
double lastAIHorizonEntropy=0.0;
double lastAIRegimeStability=0.50;
double lastAIMetaProbability=0.50;
double lastAICrossTimeframeScore=0.0;
double lastAIAdaptiveRate=1.0;
double lastAIHierarchicalPrior=0.50;
double lastAIDriftScore=0.0;
double lastAISpecialistConsensus=0.50;
double lastAIEntropyConfidence=0.50;
bool lastBreakoutDetected=false;
double lastBreakoutStrength=0.0;
long aiHistoryProcessed=0;
long aiHistoryTarget=0;
int aiHistoryNextShift=2;
datetime aiHistoryOldestTime=0;
bool aiHistoryComplete=false;
int aiHistoryBatchCount=0;
long aiHistoryEpoch=0;
long aiHistoryUniqueAvailable=0;
long aiHistoryDeepSamples=0;
double aiHistoryThroughput=0.0;
ulong aiHistoryRateWindowStartMs=0;
long aiHistoryRateWindowSamples=0;
ulong aiHistoryLastPassMs=0;
ulong aiLastMemorySaveMs=0;
ulong aiLastStateSaveMs=0;
bool aiStateLoaded=false;
double lastMemoryProbability=0.50;
double lastMemoryConfidence=0.0;
int lastMemoryBucket=-1;
double lastATR=0.0;
double lastVolatilityPercentile=50.0;
double lastVolatilityRatio=1.0;
double lastRSI=50.0;
bool lastRSIDirectionalIdeal=true;
double lastBBUpper=0.0;
double lastBBMiddle=0.0;
double lastBBLower=0.0;
double lastBBPosition=0.0;
double lastIndicatorScore=0.0;
double lastStrategyScore=0.0;
double lastDirectScore=0.0;
double lastAdvancedScore=0.0;
double lastAdvancedAgreement=0.0;
double lastAgreement=0.0;
double lastDirectAgreement=0.0;
double lastFinalScore=0.0;
int lastStrategyCount=0;
int lastDirectCount=0;
int lastDirectBuyVotes=0;
int lastDirectSellVotes=0;
int lastDirectNeutralVotes=0;
int lastAdvancedBuyVotes=0;
int lastAdvancedSellVotes=0;
int lastAdvancedNeutralVotes=0;
int lastSignal=0;
int confirmedM1Direction=0;
datetime confirmedDirectionStartBar=0;
datetime lastDirectionEvaluationBar=0;
int lastDirectionHoldBars=0;
int lastBullishConfirmCount=0;
int lastBearishConfirmCount=0;
int lastTrendBuyVotes=0;
int lastTrendSellVotes=0;
double lastTrendStrength=0.0;
string lastDirectionSource="BEKLE";
string lastStatus="BASLATILIYOR";
ulong lastEntryMs=0;
ulong lastFridayCloseMs=0;
ulong lastProfitCloseMs=0;
double lastBasketProfit=0.0;
double gBasketPeakProfit=0.0;
double gBasketPeakGiveback=0.0;
bool   gPeakProfitArmed=false;
double gProfitVelocityEma=0.0;
double gPreviousProfitVelocity=0.0;
double gPreviousBasketProfit=0.0;
double gDynamicPeakGivebackPct=0.0;
ulong  gPreviousProfitSampleMs=0;
ulong  gLastAIProfitEvalMs=0;
double gAIProfitDirectionConfidence=0.50;
bool   gAIProfitReversal=false;
int    lastLiveEntryAgeSeconds=-1;
bool basketTakeProfitClosing=false;
bool continuousFillBusy=false;
datetime lastSingleEntryBar=0;
int spreadSamples[];
int spreadSampleIndex=0;
int spreadSampleCount=0;
int lastCurrentSpread=-1;
int lastMinimumSpread=-1;
double lastObservedBid=0.0;
int tickDirections[128];
int tickDirectionIndex=0;
int tickDirectionCount=0;
double lastTickImbalance=0.0;
double lastExecutionSlippage=0.0;
double averageExecutionSlippage=0.0;

string gEngineSymbol="";
string gForexSymbols[];
int gUniverseMinimumSpread[];
int gUniverseSpreadSamples[];
bool gActiveHadPositions=false;
bool gFastRefillAfterFlat=false;
bool gNeedSymbolScan=true;
bool gModelInitialized=false;
ulong gLastUniverseScanMs=0;
ulong gSelectionTimeMs=0;
double gSelectedScanScore=0.0;
double gSelectedScanVolatility=50.0;
double gSelectedScanRSI=50.0;
int gSelectedScanDirection=0;
string gSelectedScanReason="TARAMA BEKLENIYOR";
string gLastOpenedSymbol="";
int gSelectedStreakCount=0;
double gSelectedExtremeQuality=0.0;
int gSelectedExtremeAnchorShift=0;

// V59 sepet durumu: bir dongude yalnizca tek parite kullanilir.
string gBasketSymbol="";
int    gBasketDirection=0;
bool   gBasketEntryComplete=false;
int    gBasketOrdersOpened=0;
bool   gBasketOrderLock=false;

struct ForexScanCandidate
{
   string symbol;
   int direction;
   double score;
   double volatilityPercentile;
   double volatilityRatio;
   bool mediumVolatility;
   double rsi;
   int spreadPoints;
   int bullishCandles;
   int bearishCandles;
   int streakCandles;
   double extremeQuality;
   string reason;
};

double ClampValue(double value,double minimum,double maximum)
{
   return MathMax(minimum,MathMin(maximum,value));
}

double SafeDivide(double numerator,double denominator)
{
   if(MathAbs(denominator)<1e-12)
      return 0.0;
   return numerator/denominator;
}

string EngineSymbol()
{
   if(gEngineSymbol!="")
      return gEngineSymbol;
   return ChartSymbol(0);
}

double EnginePoint()
{
   double point=SymbolInfoDouble(EngineSymbol(),SYMBOL_POINT);
   return point>0.0?point:0.00001;
}

int EngineDigits()
{
   return (int)SymbolInfoInteger(EngineSymbol(),SYMBOL_DIGITS);
}


bool IsExcludedSlowSymbol(string symbol)
{
   string upper=symbol;
   StringToUpper(upper);

   // ZARJPY is intentionally excluded as a slow-moving pair.
   // This also catches broker suffix/prefix variants such as ZARJPYm or ZARJPY.a.
   if(StringFind(upper,"ZARJPY")>=0)
      return true;

   return false;
}

bool IsForexSymbolName(string symbol)
{
   if(IsExcludedSlowSymbol(symbol))
      return false;
   if(symbol=="")
      return false;

   string baseCurrency=SymbolInfoString(symbol,SYMBOL_CURRENCY_BASE);
   string profitCurrency=SymbolInfoString(symbol,SYMBOL_CURRENCY_PROFIT);
   ENUM_SYMBOL_CALC_MODE calculationMode=
      (ENUM_SYMBOL_CALC_MODE)SymbolInfoInteger(symbol,SYMBOL_TRADE_CALC_MODE);
   long tradeMode=SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE);

   bool forexMode=calculationMode==SYMBOL_CALC_MODE_FOREX ||
                  calculationMode==SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE;
   bool tradable=tradeMode!=SYMBOL_TRADE_MODE_DISABLED &&
                 tradeMode!=SYMBOL_TRADE_MODE_CLOSEONLY;

   return forexMode && tradable && StringLen(baseCurrency)==3 &&
          StringLen(profitCurrency)==3 && baseCurrency!=profitCurrency;
}

bool IsForexSymbol()
{
   return IsForexSymbolName(EngineSymbol());
}

int BuildForexUniverse()
{
   ArrayResize(gForexSymbols,0);
   ArrayResize(gUniverseMinimumSpread,0);
   ArrayResize(gUniverseSpreadSamples,0);

   int total=SymbolsTotal(false);
   int count=0;

   for(int i=0;i<total;i++)
   {
      string symbol=SymbolName(i,false);
      if(!IsForexSymbolName(symbol))
         continue;

      if(!SymbolSelect(symbol,true))
         continue;

      ArrayResize(gForexSymbols,count+1);
      ArrayResize(gUniverseMinimumSpread,count+1);
      ArrayResize(gUniverseSpreadSamples,count+1);
      gForexSymbols[count]=symbol;
      gUniverseMinimumSpread[count]=2147483647;
      gUniverseSpreadSamples[count]=0;
      count++;
   }

   return count;
}

double ScannerATRAt(MqlRates &rates[],int shift,int period)
{
   int size=ArraySize(rates);
   if(period<=0 || shift<0 || shift+period>=size)
      return 0.0;

   double total=0.0;
   for(int i=shift;i<shift+period;i++)
   {
      double previousClose=rates[i+1].close;
      double trueRange=MathMax(rates[i].high-rates[i].low,
                       MathMax(MathAbs(rates[i].high-previousClose),
                               MathAbs(rates[i].low-previousClose)));
      total+=trueRange;
   }

   return total/period;
}

double ScannerRSI(MqlRates &rates[],int shift,int period)
{
   int size=ArraySize(rates);
   if(period<=0 || shift<0 || shift+period>=size)
      return 50.0;

   double gains=0.0;
   double losses=0.0;
   for(int i=shift;i<shift+period;i++)
   {
      double change=rates[i].close-rates[i+1].close;
      if(change>0.0) gains+=change;
      else losses-=change;
   }

   if(losses<=0.0)
      return gains>0.0?100.0:50.0;

   double relativeStrength=gains/losses;
   return 100.0-(100.0/(1.0+relativeStrength));
}


double MultiHorizonDirectionScore(MqlRates &rates[],int startShift,
                                  int requestedHorizons,double &agreement)
{
   agreement=0.0;
   int size=ArraySize(rates);
   int maximum=MathMin(requestedHorizons,size-startShift-1);
   if(maximum<1) return 0.0;

   double averageRange=0.0;
   int rangeCount=0;
   int rangeMax=MathMin(24,size-startShift-1);
   for(int i=0;i<rangeMax;i++)
   {
      int idx=startShift+i;
      averageRange+=MathMax(1e-12,rates[idx].high-rates[idx].low);
      rangeCount++;
   }
   if(rangeCount<=0) return 0.0;
   averageRange/=rangeCount;

   double weighted=0.0;
   double weightTotal=0.0;
   double directionalStrength=0.0;
   int positive=0;
   int negative=0;

   for(int horizon=1;horizon<=maximum;horizon++)
   {
      int older=startShift+horizon;
      double move=rates[startShift].close-rates[older].close;
      double scale=MathMax(averageRange,averageRange*MathSqrt((double)horizon));
      double normalized=MathTanh(move/scale);

      // Zamansal dikkat: hem yakin tepkiyi hem de daha uzun trendi koru.
      double weight=1.0/MathSqrt((double)horizon);
      if(horizon>=12)  weight*=1.05;
      if(horizon>=24)  weight*=1.08;
      if(horizon>=48)  weight*=1.10;
      if(horizon>=72)  weight*=1.12;
      if(horizon>=96)  weight*=1.14;
      if(horizon>=120) weight*=1.16;
      if(horizon>=160) weight*=1.18;
      if(horizon>=192) weight*=1.20;
      if(horizon>=224) weight*=1.22;
      if(horizon>=256) weight*=1.24;
      if(horizon>=288) weight*=1.25;
      if(horizon>=320) weight*=1.26;
      if(horizon>=352) weight*=1.27;

      // Guclu ama tutarli ufuklara dikkat artar; tek bir asiri harekete teslim olmaz.
      double attention=0.72+0.28*MathAbs(normalized);
      weight*=attention;

      weighted+=weight*normalized;
      directionalStrength+=weight*MathAbs(normalized);
      weightTotal+=weight;
      if(move>0.0) positive++;
      else if(move<0.0) negative++;
   }

   if(weightTotal<=0.0) return 0.0;
   int directional=positive+negative;
   if(directional>0)
      agreement=(double)MathMax(positive,negative)/directional;

   double raw=weighted/weightTotal;
   double strength=directionalStrength/weightTotal;
   // Zayif ve kararsiz rejimde skoru merkeze cek.
   double quality=ClampValue(0.35+0.45*agreement+0.20*strength,0.25,1.0);
   return ClampValue(raw*quality,-1.0,1.0);
}

double AIRegimeStabilityFromRates(MqlRates &rates[],int startShift,
                                      double &directionScore)
{
   if(!AI_Rejim_Istikrar)
   {
      double agreement=0.0;
      directionScore=MultiHorizonDirectionScore(rates,startShift,AI_MULTI_HORIZONS,agreement);
      return agreement;
   }

   int horizons[12]={6,12,18,24,36,48,72,96,144,192,288,384};
   double weights[12]={0.055,0.065,0.075,0.085,0.09,0.10,0.105,0.105,0.09,0.08,0.075,0.075};
   double scoreTotal=0.0;
   double weightTotal=0.0;
   double agreementTotal=0.0;
   double mean=0.0;
   double meanSquare=0.0;
   int positive=0;
   int negative=0;
   int used=0;

   for(int i=0;i<12;i++)
   {
      if(startShift+horizons[i]>=ArraySize(rates))
         continue;

      double agreement=0.0;
      double score=MultiHorizonDirectionScore(rates,startShift,horizons[i],agreement);
      double weight=weights[i];
      scoreTotal+=weight*score;
      agreementTotal+=weight*agreement;
      weightTotal+=weight;
      mean+=score;
      meanSquare+=score*score;
      if(score>0.0) positive++;
      else if(score<0.0) negative++;
      used++;
   }

   if(used<=0 || weightTotal<=0.0)
   {
      directionScore=0.0;
      return 0.50;
   }

   directionScore=ClampValue(scoreTotal/weightTotal,-1.0,1.0);
   double signConsensus=(double)MathMax(positive,negative)/MathMax(1,positive+negative);
   double averageAgreement=ClampValue(agreementTotal/weightTotal,0.0,1.0);
   mean/=used;
   meanSquare/=used;
   double dispersion=MathSqrt(MathMax(0.0,meanSquare-mean*mean));
   double smoothness=1.0-ClampValue(dispersion/0.65,0.0,1.0);

   return ClampValue(0.42*signConsensus+
                     0.38*averageAgreement+
                     0.20*smoothness,0.0,1.0);
}

double AITemporalPriorProbability(MqlRates &rates[],int startShift,
                                  double &regimeConsensus)
{
   double regimeScore=0.0;
   regimeConsensus=AIRegimeStabilityFromRates(rates,startShift,regimeScore);

   // Istikrarlı rejimde uzun ufuk bilgisine daha fazla, kararsız rejimde daha az güven.
   double temperature=1.55+1.20*regimeConsensus;
   return ClampValue(AISigmoid(temperature*regimeScore),0.02,0.98);
}


double AIEntropyConfidence(double probability)
{
   double p=ClampValue(probability,0.000001,0.999999);
   double entropy=-(p*MathLog(p)+(1.0-p)*MathLog(1.0-p))/MathLog(2.0);
   return ClampValue(1.0-entropy,0.0,1.0);
}

double AIHierarchicalRegimeProbability(MqlRates &rates[],int startShift,
                                       double &specialistConsensus)
{
   specialistConsensus=0.50;
   if(!AI_Hiyerarsik_Rejim)
   {
      double agreement=0.0;
      double score=MultiHorizonDirectionScore(rates,startShift,AI_MULTI_HORIZONS,agreement);
      specialistConsensus=agreement;
      return ClampValue(AISigmoid(2.0*score),0.02,0.98);
   }

   int horizons[12]={6,12,18,24,36,48,72,96,144,192,288,384};
   double baseWeights[12]={0.075,0.085,0.09,0.095,0.10,0.105,
                           0.105,0.095,0.075,0.065,0.055,0.045};
   double weightedProbability=0.0;
   double weightTotal=0.0;
   double weightedAgreement=0.0;
   int positive=0,negative=0,used=0;

   for(int i=0;i<AI_REGIME_EXPERTS;i++)
   {
      if(startShift+horizons[i]>=ArraySize(rates))
         continue;

      double agreement=0.0;
      double score=MultiHorizonDirectionScore(rates,startShift,horizons[i],agreement);
      double strength=MathAbs(score);
      double expertReliability=ClampValue(0.35+0.45*agreement+0.20*strength,0.20,1.0);
      double weight=baseWeights[i]*expertReliability;
      double temperature=1.40+1.10*agreement+0.40*strength;
      double probability=AISigmoid(temperature*score);

      weightedProbability+=weight*probability;
      weightedAgreement+=weight*agreement;
      weightTotal+=weight;
      if(score>0.015) positive++;
      else if(score<-0.015) negative++;
      used++;
   }

   if(weightTotal<=0.0 || used<=0)
      return 0.50;

   double signConsensus=(double)MathMax(positive,negative)/MathMax(1,positive+negative);
   double agreementConsensus=ClampValue(weightedAgreement/weightTotal,0.0,1.0);
   specialistConsensus=ClampValue(0.58*signConsensus+0.42*agreementConsensus,0.0,1.0);

   double probability=weightedProbability/weightTotal;
   // Uzmanlar uyusmuyorsa asiri guveni merkeze cek.
   double shrink=0.45+0.55*specialistConsensus;
   return ClampValue(0.50+(probability-0.50)*shrink,0.02,0.98);
}

double AIMarketDriftScore(MqlRates &rates[],int startShift)
{
   if(!AI_Drift_Farkindalik)
      return 0.0;

   int size=ArraySize(rates);
   if(startShift+140>=size)
      return 0.0;

   double recentRange=0.0,olderRange=0.0;
   for(int i=0;i<16;i++)
      recentRange+=MathMax(1e-12,rates[startShift+i].high-rates[startShift+i].low);
   for(int i=48;i<112;i++)
      olderRange+=MathMax(1e-12,rates[startShift+i].high-rates[startShift+i].low);
   recentRange/=16.0;
   olderRange/=64.0;

   double volatilityShift=MathAbs(MathLog(MathMax(1e-9,recentRange)/MathMax(1e-9,olderRange)));

   double recentAgreement=0.0,longAgreement=0.0;
   double recentScore=MultiHorizonDirectionScore(rates,startShift,24,recentAgreement);
   double longScore=MultiHorizonDirectionScore(rates,startShift,128,longAgreement);
   double directionShift=MathAbs(recentScore-longScore)*0.50;
   double agreementShift=MathAbs(recentAgreement-longAgreement);

   double recentBody=0.0,olderBody=0.0;
   for(int i=0;i<16;i++)
      recentBody+=MathAbs(rates[startShift+i].close-rates[startShift+i].open);
   for(int i=48;i<112;i++)
      olderBody+=MathAbs(rates[startShift+i].close-rates[startShift+i].open);
   recentBody/=16.0;
   olderBody/=64.0;
   double bodyShift=MathAbs(MathLog(MathMax(1e-9,recentBody)/MathMax(1e-9,olderBody)));

   return ClampValue(0.34*volatilityShift+
                     0.34*directionShift+
                     0.18*agreementShift+
                     0.14*bodyShift,0.0,1.0);
}

bool BreakoutDetectedInRates(MqlRates &rates[],int shift,double &strength)
{
   strength=0.0;
   if(!InpUseBreakoutGuard) return false;

   int size=ArraySize(rates);
   int lookback=MathMax(10,MathMin(60,InpBreakoutLookback));
   if(shift<0 || shift+lookback+15>=size) return false;

   double atr=ScannerATRAt(rates,shift+1,14);
   if(atr<=0.0) return false;

   double priorHigh=rates[shift+1].high;
   double priorLow=rates[shift+1].low;
   for(int i=shift+2;i<=shift+lookback;i++)
   {
      if(rates[i].high>priorHigh) priorHigh=rates[i].high;
      if(rates[i].low<priorLow) priorLow=rates[i].low;
   }

   double closePrice=rates[shift].close;
   double channelExcess=0.0;
   if(closePrice>priorHigh)
      channelExcess=(closePrice-priorHigh)/atr;
   else if(closePrice<priorLow)
      channelExcess=(priorLow-closePrice)/atr;

   bool channelBreak=channelExcess>=MathMax(0.0,InpBreakoutChannelATR);

   double candleRange=MathMax(0.0,rates[shift].high-rates[shift].low);
   double body=MathAbs(rates[shift].close-rates[shift].open);
   double bodyRatio=candleRange>0.0?body/candleRange:0.0;
   double rangeATR=candleRange/atr;
   bool expansionBreak=rangeATR>=MathMax(1.0,InpBreakoutRangeATR) &&
                       bodyRatio>=0.60;

   double velocityATR=0.0;
   if(shift+3<size)
      velocityATR=MathAbs(rates[shift].close-rates[shift+3].close)/atr;
   bool velocityBreak=velocityATR>=MathMax(1.0,InpBreakoutVelocityATR);

   strength=MathMax(channelExcess,
                    MathMax(rangeATR/MathMax(1.0,InpBreakoutRangeATR),
                            velocityATR/MathMax(1.0,InpBreakoutVelocityATR)));
   return channelBreak || expansionBreak || velocityBreak;
}

bool CurrentBreakoutBlocked()
{
   lastBreakoutDetected=false;
   lastBreakoutStrength=0.0;
   if(!InpUseBreakoutGuard) return false;

   MqlRates bars[];
   ArraySetAsSeries(bars,true);
   int needed=MathMax(60,InpBreakoutLookback+20);
   if(CopyRates(EngineSymbol(),InpTF,0,needed,bars)<needed)
      return false;

   double s0=0.0,s1=0.0;
   bool b0=BreakoutDetectedInRates(bars,0,s0);
   bool b1=BreakoutDetectedInRates(bars,1,s1);
   lastBreakoutDetected=b0 || b1;
   lastBreakoutStrength=MathMax(s0,s1);
   return lastBreakoutDetected;
}



bool CandleOpenDistanceReached(string symbol,int direction,double &distancePoints)
{
   distancePoints=0.0;
   if(direction==0)
      return false;

   MqlRates live[];
   ArraySetAsSeries(live,true);
   if(CopyRates(symbol,InpTF,0,1,live)!=1)
      return false;

   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick) || tick.bid<=0.0 || tick.ask<=0.0)
      return false;

   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   if(point<=0.0)
      return false;

   double currentPrice=(direction>0 ? tick.ask : tick.bid);
   double rawDistance=(direction>0 ?
                       currentPrice-live[0].open :
                       live[0].open-currentPrice);

   distancePoints=rawDistance/point;
   return distancePoints>=MathMax(0.0,InpEntryDistancePoints);
}

int CurrentLiveCandleColorDirection(string symbol)
{
   MqlRates live[];
   ArraySetAsSeries(live,true);
   if(CopyRates(symbol,InpTF,0,1,live)!=1)
      return 0;

   if(live[0].close>live[0].open)
      return 1;
   if(live[0].close<live[0].open)
      return -1;

   return 0;
}

int LiveCandleColorFirstSeconds(string symbol,int &ageSeconds)
{
   ageSeconds=-1;
   MqlRates live[];
   ArraySetAsSeries(live,true);
   if(CopyRates(symbol,InpTF,0,1,live)!=1)
      return 0;

   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick))
      return 0;

   datetime nowTime=tick.time>0?tick.time:TimeTradeServer();
   ageSeconds=(int)(nowTime-live[0].time);
   int limit=MathMax(1,InpEntryFirstSeconds);
   if(ageSeconds<0 || ageSeconds>limit)
      return 0;

   // Canli mum yesilse BUY, kirmiziysa SELL. Doji ise renk olusana kadar bekle.
   if(live[0].close>live[0].open)
      return 1;
   if(live[0].close<live[0].open)
      return -1;
   return 0;
}



bool DetectTwelveCandleDirectionSignal(string symbol,
                                        MqlRates &rates[],
                                        int &direction,
                                        int &windowBars,
                                        int &anchorShift,
                                        double &directionQuality)
{
   direction=0;
   windowBars=0;
   anchorShift=0;
   directionQuality=0.0;

   int window=MathMax(2,MathMin(60,InpDirectionWindow));
   int lookback=MathMax(window+2,MathMin(120,InpDirectionLookback));

   // rates[0] canli mum, rates[1] son kapanmis mumdur.
   // 12 mumun AYNI RENK veya ARDISIK YONDE olmasi gerekmez.
   if(ArraySize(rates)<lookback+2)
      return false;

   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   if(point<=0.0)
      return false;

   // Son 12 kapanmis mumun net yonu: en eski mumun acilisindan
   // en yeni kapanisa kadar toplam hareket.
   double startPrice=rates[window].open;
   double endPrice=rates[1].close;
   double netMove=endPrice-startPrice;

   // Son 12 mum icindeki dip/tepeyi kalite ve referans icin bul.
   int lowestShift=1;
   int highestShift=1;
   double lowestLow=rates[1].low;
   double highestHigh=rates[1].high;
   double totalPath=0.0;
   int bullish=0;
   int bearish=0;

   for(int i=1;i<=window;i++)
   {
      if(rates[i].low<lowestLow)
      {
         lowestLow=rates[i].low;
         lowestShift=i;
      }
      if(rates[i].high>highestHigh)
      {
         highestHigh=rates[i].high;
         highestShift=i;
      }
      if(rates[i].close>rates[i].open) bullish++;
      else if(rates[i].close<rates[i].open) bearish++;

      if(i<window)
         totalPath+=MathAbs(rates[i].close-rates[i+1].close);
   }

   double averageRange=0.0;
   for(int i=1;i<=window;i++)
      averageRange+=MathMax(point,rates[i].high-rates[i].low);
   averageRange/=window;

   // Canli mum yonu yedek sinyaldir. 12 mumluk net hareket cok zayifsa
   // bot canli mumun yonunde de islem acabilir; bu sayede sinyal kilitlenmez.
   int liveDirection=0;
   if(rates[0].close>rates[0].open) liveDirection=1;
   else if(rates[0].close<rates[0].open) liveDirection=-1;

   double weakThreshold=MathMax(point*0.10,averageRange*0.08);
   if(netMove>weakThreshold)
      direction=1;
   else if(netMove<-weakThreshold)
      direction=-1;
   else
      direction=liveDirection;

   if(direction==0)
      return false;

   // "En dusukten yukari" BUY, "yukardan asagi" SELL referansi.
   // Ancak dip/tepenin tam 12 mum once olmasi zorunlu degildir.
   anchorShift=direction>0?lowestShift:highestShift;
   windowBars=window;

   double efficiency=SafeDivide(MathAbs(netMove),MathMax(point,totalPath));
   double directionalShare=direction>0?
                           (double)bullish/window:
                           (double)bearish/window;

   // Ard arda olma zorunlulugu YOK; sadece net yon ve mum baskisi kaliteye girer.
   directionQuality=ClampValue(0.65*efficiency+0.35*directionalShare,0.0,1.0);
   if(MathAbs(netMove)<=weakThreshold && liveDirection!=0)
      directionQuality=MathMax(directionQuality,0.25);

   return true;
}

bool DetectExtremeTrend8To20(MqlRates &rates[],
                             int &direction,
                             int &trendBars,
                             int &anchorShift,
                             double &trendQuality)
{
   direction=0;
   trendBars=0;
   anchorShift=0;
   trendQuality=0.0;

   int size=ArraySize(rates);
   int maximumShift=MathMin(20,size-1);
   if(maximumShift<8)
      return false;

   // Son 20 kapanmis mum icindeki GERCEK en dusuk ve en yuksek noktayi bul.
   // rates[1] en son kapanmis mum, shift buyudukce gecmise gider.
   int lowestShift=1;
   int highestShift=1;
   double lowestLow=rates[1].low;
   double highestHigh=rates[1].high;

   for(int i=2;i<=maximumShift;i++)
   {
      if(rates[i].low<lowestLow)
      {
         lowestLow=rates[i].low;
         lowestShift=i;
      }

      if(rates[i].high>highestHigh)
      {
         highestHigh=rates[i].high;
         highestShift=i;
      }
   }

   bool buyValid=lowestShift>=8 && lowestShift<=20 &&
                 rates[1].close>lowestLow;
   bool sellValid=highestShift>=8 && highestShift<=20 &&
                  rates[1].close<highestHigh;

   double buyQuality=-1000000.0;
   double sellQuality=-1000000.0;

   if(buyValid)
   {
      int steps=MathMax(1,lowestShift-1);
      int risingSteps=0;
      double path=0.0;

      for(int i=lowestShift-1;i>=1;i--)
      {
         double change=rates[i].close-rates[i+1].close;
         path+=MathAbs(change);
         if(change>0.0)
            risingSteps++;
      }

      double netMove=rates[1].close-rates[lowestShift].close;
      double consistency=(double)risingSteps/steps;
      double efficiency=path>0.0?MathMax(0.0,netMove/path):0.0;

      // 2+3 mumluk surecte genel hareket yukari olmali. Her mumun yesil
      // olmasi gerekmez; dipten itibaren yukari ilerleme esas alinir.
      buyValid=netMove>0.0 && consistency>=0.50;
      if(buyValid)
         buyQuality=consistency+ClampValue(efficiency,0.0,1.0);
   }

   if(sellValid)
   {
      int steps=MathMax(1,highestShift-1);
      int fallingSteps=0;
      double path=0.0;

      for(int i=highestShift-1;i>=1;i--)
      {
         double change=rates[i].close-rates[i+1].close;
         path+=MathAbs(change);
         if(change<0.0)
            fallingSteps++;
      }

      double netMove=rates[highestShift].close-rates[1].close;
      double consistency=(double)fallingSteps/steps;
      double efficiency=path>0.0?MathMax(0.0,netMove/path):0.0;

      // 2+3 mumluk surecte genel hareket asagi olmali. Her mumun kirmizi
      // olmasi gerekmez; tepeden itibaren asagi ilerleme esas alinir.
      sellValid=netMove>0.0 && consistency>=0.50;
      if(sellValid)
         sellQuality=consistency+ClampValue(efficiency,0.0,1.0);
   }

   if(!buyValid && !sellValid)
      return false;

   if(buyValid && (!sellValid || buyQuality>=sellQuality))
   {
      direction=1;
      trendBars=lowestShift;
      anchorShift=lowestShift;
      trendQuality=ClampValue(buyQuality/2.0,0.0,1.0);
      return true;
   }

   direction=-1;
   trendBars=highestShift;
   anchorShift=highestShift;
   trendQuality=ClampValue(sellQuality/2.0,0.0,1.0);
   return true;
}


int MarketGuardSecondsOfDay(datetime value)
{
   MqlDateTime part;
   TimeToStruct(value,part);
   return part.hour*3600+part.min*60+part.sec;
}

datetime ReliableBrokerTime()
{
   datetime now=TimeTradeServer();
   if(now<=0)
      now=TimeCurrent();
   return now;
}

bool SymbolWeeklyWindowOpenNow()
{
   if(!InpUseWeeklySchedule)
      return true;

   MqlDateTime p;
   TimeToStruct(ReliableBrokerTime(),p);

   int nowMinute=p.hour*60+p.min;
   int mondayOpen=MathMax(0,MathMin(23,InpMondayOpenHour))*60+
                  MathMax(0,MathMin(59,InpMondayOpenMinute));
   int fridayClose=MathMax(0,MathMin(23,InpFridayCloseHour))*60+
                   MathMax(0,MathMin(59,InpFridayCloseMinute));

   if(p.day_of_week==0 || p.day_of_week==6)
      return false;
   if(p.day_of_week==1 && nowMinute<mondayOpen)
      return false;
   if(p.day_of_week==5 && nowMinute>=fridayClose)
      return false;

   return true;
}

bool BrokerSymbolSessionOpen(string symbol)
{
   datetime now=ReliableBrokerTime();
   MqlDateTime p;
   TimeToStruct(now,p);

   // Cumartesi/Pazar broker seans verisi hatali olsa bile kapali kabul et.
   if(p.day_of_week==0 || p.day_of_week==6)
      return false;

   ENUM_DAY_OF_WEEK weekday=(ENUM_DAY_OF_WEEK)p.day_of_week;
   int nowSeconds=p.hour*3600+p.min*60+p.sec;
   bool found=false;

   for(uint sessionIndex=0;sessionIndex<32;sessionIndex++)
   {
      datetime from=0,to=0;
      if(!SymbolInfoSessionTrade(symbol,weekday,sessionIndex,from,to))
         break;

      found=true;
      int fromSeconds=MarketGuardSecondsOfDay(from);
      int toSeconds=MarketGuardSecondsOfDay(to);

      // Bazı brokerlarda 00:00-00:00 tum gun anlamina gelebilir.
      if(fromSeconds==toSeconds)
         return true;

      if(toSeconds==0 && fromSeconds>0)
         toSeconds=86400;

      bool inside=false;
      if(fromSeconds<toSeconds)
         inside=(nowSeconds>=fromSeconds && nowSeconds<toSeconds);
      else
         inside=(nowSeconds>=fromSeconds || nowSeconds<toSeconds);

      if(inside)
         return true;
   }

   // Bazi Forex brokerlari SymbolInfoSessionTrade verisini hic yayinlamaz.
   // Seans verisi YOKSA bu tek basina piyasayi kapali saymaz.
   // Kapali piyasa yine hafta sonu + trade mode + BAYAT TICK ile engellenir.
   if(!found)
      return true;

   // Seans verisi bulundu fakat mevcut saat hicbir seansin icinde degil.
   return false;
}

bool FreshTradableMarketTick(string symbol,MqlTick &tick)
{
   if(!SymbolInfoTick(symbol,tick))
      return false;

   if(tick.bid<=0.0 || tick.ask<=tick.bid || tick.time<=0)
      return false;

   datetime now=ReliableBrokerTime();
   long age=(long)now-(long)tick.time;

   // Gelecek zamanli veya eski tick kabul edilmez.
   int maximumAge=MathMax(5,InpMaxTickAgeSeconds);
   if(age<0 || age>maximumAge)
      return false;

   long tradeMode=SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE);
   if(tradeMode==SYMBOL_TRADE_MODE_DISABLED ||
      tradeMode==SYMBOL_TRADE_MODE_CLOSEONLY)
      return false;

   if(InpStrictClosedMarketGuard)
   {
      if(!SymbolWeeklyWindowOpenNow())
         return false;

      if(!BrokerSymbolSessionOpen(symbol))
         return false;
   }

   return true;
}

bool StrictMarketOpenForSymbol(string symbol)
{
   MqlTick tick;
   return FreshTradableMarketTick(symbol,tick);
}


double ScannerEMAAt(MqlRates &rates[],int shift,int period)
{
   int total=ArraySize(rates);
   period=MathMax(2,period);
   int oldest=MathMin(total-1,shift+period*4);
   if(oldest<=shift)
      return 0.0;

   double alpha=2.0/(period+1.0);
   double ema=rates[oldest].close;
   for(int i=oldest-1;i>=shift;i--)
      ema=alpha*rates[i].close+(1.0-alpha)*ema;

   return ema;
}

int ScannerEMA42TrendDirection(MqlRates &rates[],double livePrice)
{
   if(!InpUseEMA42TrendFilter)
      return 0;

   double emaNow=ScannerEMAAt(rates,0,MathMax(2,InpTrendEMAPeriod));
   double emaPrev=ScannerEMAAt(rates,1,MathMax(2,InpTrendEMAPeriod));
   if(emaNow<=0.0 || emaPrev<=0.0)
      return 0;

   double point=0.0;
   // Scanner generic oldugu icin point yerine EMA'nin mutlak farkini kullan;
   // minimum slope 0 ise her pozitif/negatif egim gecerlidir.
   double minSlope=0.0;
   if(InpEMA42MinSlopePoints>0.0)
   {
      double priceScale=MathMax(0.00000001,MathAbs(livePrice)*1.0e-6);
      minSlope=InpEMA42MinSlopePoints*priceScale;
   }

   double slope=emaNow-emaPrev;
   if(slope>minSlope)
      return 1;
   if(slope<-minSlope)
      return -1;
   return 0;
}

bool EvaluateForexScanCandidate(int universeIndex,
                                ForexScanCandidate &candidate)
{
   if(universeIndex<0 || universeIndex>=ArraySize(gForexSymbols))
      return false;

   string symbol=gForexSymbols[universeIndex];
   if(IsExcludedSlowSymbol(symbol))
      return false;


   // V76 SUREKLI ISLEM:
   // Onceki sepetin ayni paritesini tekrar kullanmak serbesttir.
   // En iyi dusuk-spread/orta-ust-vol aday ayni sembolse yeniden secilebilir.

   MqlTick tick;
   if(!FreshTradableMarketTick(symbol,tick))
      return false;

   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   if(point<=0.0)
      return false;

   int spreadPoints=(int)MathRound((tick.ask-tick.bid)/point);
   if(InpMaxSpreadPoints>0 && spreadPoints>InpMaxSpreadPoints)
      return false;

   gUniverseSpreadSamples[universeIndex]++;
   if(spreadPoints<gUniverseMinimumSpread[universeIndex])
      gUniverseMinimumSpread[universeIndex]=spreadPoints;

   MqlRates rates[];
   ArraySetAsSeries(rates,true);
   int requested=MathMax(AI_MULTI_HORIZONS+30,InpDirectionLookback+30);
   int copied=CopyRates(symbol,InpTF,0,requested,rates);
   if(copied<MathMax(60,InpDirectionLookback+5))
      return false;

   double breakoutLive=0.0,breakoutClosed=0.0;
   if(BreakoutDetectedInRates(rates,0,breakoutLive) ||
      BreakoutDetectedInRates(rates,1,breakoutClosed))
      return false;

   int direction=0;
   int confirmCount=1;
   int anchorShift=0;
   double extremeQuality=0.0;

   // V91: Surekli giris aciksa M15 mumunun herhangi bir aninda EMA42 egimine gore
   // aday secilebilir. Surekli giris kapaliysa klasik ilk-N-saniye penceresi kullanilir.
   int candleAge=(int)((tick.time>0?tick.time:TimeTradeServer())-rates[0].time);
   int entryLimit=MathMax(1,InpEntryFirstSeconds);
   if(candleAge<0)
      return false;
   if(!InpContinuousEntryAnyTime && candleAge>entryLimit)
      return false;

   // V91: EMA42 egimi ve canli M15 mum rengi ayni yonde olmali.
   // EMA42 yukari + yesil mum = BUY.
   // EMA42 asagi  + kirmizi mum = SELL.
   double candidateLivePrice=(tick.bid+tick.ask)*0.5;
   int scannerEMA42Direction=ScannerEMA42TrendDirection(rates,candidateLivePrice);
   if(scannerEMA42Direction==0)
      return false;

   int scannerCandleDirection=0;
   if(rates[0].close>rates[0].open)
      scannerCandleDirection=1;
   else if(rates[0].close<rates[0].open)
      scannerCandleDirection=-1;
   else
      return false;

   if(scannerCandleDirection!=scannerEMA42Direction)
      return false;

   direction=scannerEMA42Direction;

   // V91: M15 mum acilisindan sinyal yonunde en az 8 point ilerlemeden aday olamaz.
   double scannerDistancePoints=0.0;
   double scannerCurrentPrice=(direction>0 ? tick.ask : tick.bid);
   double scannerRawDistance=(direction>0 ?
                              scannerCurrentPrice-rates[0].open :
                              rates[0].open-scannerCurrentPrice);
   scannerDistancePoints=scannerRawDistance/point;

   if(scannerDistancePoints<MathMax(0.0,InpEntryDistancePoints))
      return false;

   double liveRange=MathMax(point,rates[0].high-rates[0].low);
   extremeQuality=ClampValue(MathAbs(rates[0].close-rates[0].open)/liveRange,0.0,1.0);

   double multiAgreement=0.0;
   double multiScore=MultiHorizonDirectionScore(rates,1,AI_MULTI_HORIZONS,
                                                multiAgreement);
   double scannerRegimeScore=0.0;
   double scannerStability=AIRegimeStabilityFromRates(rates,1,scannerRegimeScore);

   // Uzun ufuklar sadece siralama puanidir; canli mum rengindeki girisi kilitlemez.
   int bullish=direction>0?1:0;
   int bearish=direction<0?1:0;
   string reason=(direction>0?
                  "EMA42 YUKARI + YESIL MUM -> BUY":
                  "EMA42 ASAGI + KIRMIZI MUM -> SELL")+
                 " | M15 "+IntegerToString(candleAge)+" SN | 8P MESAFE | "+(InpContinuousEntryAnyTime?"SUREKLI GIRIS":"ILK PENCERE");

   double currentATR=ScannerATRAt(rates,1,14);
   if(currentATR<=0.0)
      return false;

   double atrValues[];
   int maximumATRShift=MathMin(180,copied-15);
   if(maximumATRShift<10)
      return false;

   ArrayResize(atrValues,maximumATRShift);
   int atrCount=0;
   int atOrBelow=0;

   for(int shift=1;shift<=maximumATRShift;shift++)
   {
      double atr=ScannerATRAt(rates,shift,14);
      if(atr<=0.0)
         continue;
      atrValues[atrCount]=atr;
      if(atr<=currentATR) atOrBelow++;
      atrCount++;
   }

   if(atrCount<10)
      return false;

   ArrayResize(atrValues,atrCount);
   ArraySort(atrValues);
   double medianATR=atrValues[atrCount/2];
   double volatilityPercentile=100.0*(double)atOrBelow/atrCount;
   double volatilityRatio=currentATR/MathMax(point,medianATR);
   double rsi=ScannerRSI(rates,1,14);

   double preferredMinPct=MathMin(InpMediumVolMinPercentile,InpMediumVolMaxPercentile);
   double preferredMaxPct=MathMax(InpMediumVolMinPercentile,InpMediumVolMaxPercentile);
   double preferredMinRatio=MathMin(InpMediumVolMinRatio,InpMediumVolMaxRatio);
   double preferredMaxRatio=MathMax(InpMediumVolMinRatio,InpMediumVolMaxRatio);

   // V70: "orta ustu hareketli" = ATR yuzdeligi ve ATR/medyan oraninda
   // orta seviyenin biraz ustu, fakat asiri/kirilma tipi volatilite degil.
   bool mediumVolatility=volatilityPercentile>=preferredMinPct &&
                         volatilityPercentile<=preferredMaxPct &&
                         volatilityRatio>=preferredMinRatio &&
                         volatilityRatio<=preferredMaxRatio;
   bool idealRSI=(direction>0 && rsi>=50.0 && rsi<=70.0) ||
                 (direction<0 && rsi>=30.0 && rsi<=50.0);

   int observedMinimum=gUniverseMinimumSpread[universeIndex];
   double spreadQuality=1.0;
   if(InpMaxSpreadPoints>0)
      spreadQuality=1.0-ClampValue((double)spreadPoints/
                                  InpMaxSpreadPoints,0.0,1.0);

   double lowestSpreadBonus=0.0;
   if(InpLowestSpreadEntry && observedMinimum<2147483647)
   {
      int spreadDistance=spreadPoints-observedMinimum;
      lowestSpreadBonus=spreadDistance<=3?0.75:-MathMin(0.75,0.05*spreadDistance);
   }

   // En yuksek puan yaklasik 68. yuzdelikte: orta-ust hareket.
   const double preferredVolCenter=88.0;
   double volatilityQuality=1.0-MathAbs(volatilityPercentile-preferredVolCenter)/35.0;
   volatilityQuality=ClampValue(volatilityQuality,0.0,1.0);

   candidate.symbol=symbol;
   candidate.direction=direction;
   double multiAlignment=direction*multiScore;
   candidate.score=3.0*extremeQuality+
                   2.0*volatilityQuality+
                   (mediumVolatility?14.0:-6.0)+
                   (idealRSI?0.50:0.0)+
                   2.0*spreadQuality+lowestSpreadBonus+
                   1.75*multiAlignment+
                   0.75*multiAgreement+
                   1.10*scannerStability;
   candidate.volatilityPercentile=volatilityPercentile;
   candidate.volatilityRatio=volatilityRatio;
   candidate.mediumVolatility=mediumVolatility;
   candidate.rsi=rsi;
   candidate.spreadPoints=spreadPoints;
   candidate.bullishCandles=bullish;
   candidate.bearishCandles=bearish;
   candidate.streakCandles=confirmCount;
   candidate.extremeQuality=extremeQuality;
   candidate.reason=reason+(mediumVolatility?" | ORTA-UST VOL":" | VOL YEDEK")+
                    " | 384UFUK "+DoubleToString(multiScore,2)+
                    "/"+DoubleToString(multiAgreement*100.0,0)+"%"+
                    " | STAB "+DoubleToString(scannerStability*100.0,0)+"%";
   return true;
}

bool SelectBestForexCandidate(ForexScanCandidate &best)
{
   bool found=false;
   ForexScanCandidate selected;
   selected.score=-1000000.0;
   selected.spreadPoints=2147483647;

   for(int i=0;i<ArraySize(gForexSymbols);i++)
   {
      ForexScanCandidate candidate;
      if(!EvaluateForexScanCandidate(i,candidate))
         continue;

      // V91 KESIN ONCELIK:
      // 1) EN DUSUK ANLIK SPREAD
      // 2) Spread esitse tercih edilen hizli/orta-ustu volatilite bandi
      // 3) Sonra AI/genel kalite skoru
      bool better=false;

      if(!found)
         better=true;
      else if(candidate.spreadPoints<selected.spreadPoints)
         better=true;
      else if(candidate.spreadPoints==selected.spreadPoints)
      {
         if(candidate.mediumVolatility && !selected.mediumVolatility)
            better=true;
         else if(candidate.mediumVolatility==selected.mediumVolatility &&
                 candidate.score>selected.score)
            better=true;
      }

      if(better)
      {
         selected=candidate;
         found=true;
      }
   }

   if(!found)
      return false;

   best=selected;
   best.reason="EN DUSUK SPREAD ONCELIK | "+best.reason;
   return true;
}

bool IsHedgingAccount()
{
   return AccountInfoInteger(ACCOUNT_MARGIN_MODE)==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
}

double NormalizeLot(double requestedLot)
{
   double minimum=SymbolInfoDouble(EngineSymbol(),SYMBOL_VOLUME_MIN);
   double maximum=SymbolInfoDouble(EngineSymbol(),SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(EngineSymbol(),SYMBOL_VOLUME_STEP);

   if(step<=0.0) step=0.01;
   if(minimum<=0.0) minimum=step;
   if(maximum<=0.0) maximum=100.0;

   double lot=ClampValue(requestedLot,minimum,maximum);
   lot=MathFloor(lot/step+1e-9)*step;

   int digits=2;
   if(step>=1.0) digits=0;
   else if(step>=0.1) digits=1;
   else if(step>=0.01) digits=2;
   else if(step>=0.001) digits=3;
   else digits=4;

   return NormalizeDouble(lot,digits);
}

bool IsOurSelectedPosition()
{
   return PositionGetString(POSITION_SYMBOL)==EngineSymbol() &&
          PositionGetInteger(POSITION_MAGIC)==InpMagic;
}

int CountOpenTrades(int direction=0)
{
   int count=0;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !IsOurSelectedPosition())
         continue;

      long type=PositionGetInteger(POSITION_TYPE);
      if(direction==0 ||
         (direction>0 && type==POSITION_TYPE_BUY) ||
         (direction<0 && type==POSITION_TYPE_SELL))
      {
         count++;
      }
   }

   return count;
}

int CountAllBotPositions(string &singleSymbol,bool &multipleSymbols)
{
   int count=0;
   singleSymbol="";
   multipleSymbols=false;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;

      string positionSymbol=PositionGetString(POSITION_SYMBOL);
      if(singleSymbol=="")
         singleSymbol=positionSymbol;
      else if(positionSymbol!=singleSymbol)
         multipleSymbols=true;
      count++;
   }

   return count;
}

int CountAllBotTrades(int direction=0)
{
   int count=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;

      long type=PositionGetInteger(POSITION_TYPE);
      if(direction==0 ||
         (direction>0 && type==POSITION_TYPE_BUY) ||
         (direction<0 && type==POSITION_TYPE_SELL))
         count++;
   }
   return count;
}

bool SymbolHasBotPosition(string symbol)
{
   if(symbol=="")
      return false;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      if(PositionGetString(POSITION_SYMBOL)==symbol)
         return true;
   }
   return false;
}

int BotBasketDirection(string symbol)
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      if(PositionGetString(POSITION_SYMBOL)!=symbol)
         continue;

      long type=PositionGetInteger(POSITION_TYPE);
      if(type==POSITION_TYPE_BUY) return 1;
      if(type==POSITION_TYPE_SELL) return -1;
   }
   return 0;
}

bool ExclusiveSymbolLockValid()
{
   // V59: aktif sepet varsa tum bot pozisyonlari ayni sembolde olmak zorunda.
   string singleSymbol="";
   bool multipleSymbols=false;
   CountAllBotPositions(singleSymbol,multipleSymbols);

   if(multipleSymbols)
   {
      lastStatus="BIRDEN FAZLA PARITE ACIK - V59 YENI GIRIS YAPMAZ";
      return false;
   }

   if(singleSymbol!="" && singleSymbol!=EngineSymbol())
   {
      lastStatus="AKTIF SEPET PARITESI: "+singleSymbol;
      return false;
   }

   return true;
}

bool UpdateSpreadSnapshot()
{
   MqlTick tick;
   if(!SymbolInfoTick(EngineSymbol(),tick))
   {
      lastStatus="FIYAT ALINAMADI";
      return false;
   }

   if(lastObservedBid>0.0 && tick.bid!=lastObservedBid)
   {
      tickDirections[tickDirectionIndex]=tick.bid>lastObservedBid?1:-1;
      tickDirectionIndex=(tickDirectionIndex+1)%128;
      if(tickDirectionCount<128)
         tickDirectionCount++;

      int tickSum=0;
      for(int i=0;i<tickDirectionCount;i++)
         tickSum+=tickDirections[i];
      lastTickImbalance=tickDirectionCount>0?
                        (double)tickSum/tickDirectionCount:0.0;
   }
   lastObservedBid=tick.bid;

   int spread=(int)MathRound((tick.ask-tick.bid)/EnginePoint());
   int capacity=MathMax(20,MathMin(20000,InpSpreadLookbackSamples));

   if(ArraySize(spreadSamples)!=capacity)
   {
      ArrayResize(spreadSamples,capacity);
      ArrayInitialize(spreadSamples,-1);
      spreadSampleIndex=0;
      spreadSampleCount=0;
      lastMinimumSpread=-1;
   }

   spreadSamples[spreadSampleIndex]=spread;
   spreadSampleIndex=(spreadSampleIndex+1)%capacity;
   if(spreadSampleCount<capacity)
      spreadSampleCount++;

   lastCurrentSpread=spread;
   lastMinimumSpread=spread;

   for(int i=0;i<spreadSampleCount;i++)
   {
      if(spreadSamples[i]>=0 && spreadSamples[i]<lastMinimumSpread)
         lastMinimumSpread=spreadSamples[i];
   }

   return true;
}

bool CheckSpread()
{
   if(lastCurrentSpread<0 && !UpdateSpreadSnapshot())
      return false;

   int spread=lastCurrentSpread;

   if(spread<InpMinSpreadPoints || spread>InpMaxSpreadPoints)
   {
      lastStatus="SPREAD UYGUN DEGIL: "+IntegerToString(spread);
      return false;
   }

   // Ilk sepet seciminde en dusuk spread kullanilir. Bir pozisyon
   // kapandiktan sonraki doldurma ise maksimum spread siniri icinde
   // bekletilmeden yapilir.
   if(InpLowestSpreadEntry && CountOpenTrades()==0 && !gFastRefillAfterFlat)
   {
      int required=MathMax(1,MathMin(ArraySize(spreadSamples),
                                    InpSpreadMinimumSamples));
      if(spreadSampleCount<required)
      {
         lastStatus="MINIMUM SPREAD OLCULUYOR: "+
                    IntegerToString(spreadSampleCount)+"/"+
                    IntegerToString(required);
         return false;
      }

      int tolerance=MathMax(0,InpSpreadTolerancePoints);
      int entrySpread=lastMinimumSpread+tolerance;
      if(spread>entrySpread)
      {
         lastStatus="EN DUSUK SPREAD BEKLENIYOR: "+
                    IntegerToString(spread)+" > "+
                    IntegerToString(entrySpread);
         return false;
      }
   }

   return true;
}

double GetBufferedValue(int handle,int shift)
{
   double value[1];

   if(handle==INVALID_HANDLE || CopyBuffer(handle,0,shift,1,value)<=0)
      return 0.0;

   return value[0];
}

double GetBufferedValueAt(int handle,int bufferIndex,int shift)
{
   double value[1];

   if(handle==INVALID_HANDLE ||
      CopyBuffer(handle,bufferIndex,shift,1,value)<=0)
      return 0.0;

   return value[0];
}

bool UpdateRSIBollingerScore(double rsi)
{
   lastRSI=rsi;
   lastIndicatorScore=0.0;

   double weightedScore=0.0;
   double totalWeight=0.0;

   if(InpUseRSI && rsi>0.0 && rsi<=100.0)
   {
      double buyLevel=ClampValue(InpRSIBuyLevel,50.0,100.0);
      double sellLevel=ClampValue(InpRSISellLevel,0.0,50.0);
      double rsiScore=0.0;

      if(rsi>=buyLevel)
         rsiScore=ClampValue((rsi-50.0)/20.0,0.10,1.0);
      else if(rsi<=sellLevel)
         rsiScore=-ClampValue((50.0-rsi)/20.0,0.10,1.0);

      double weight=MathMax(0.0,InpRSIWeight);
      weightedScore+=weight*rsiScore;
      totalWeight+=weight;
   }

   lastBBMiddle=GetBufferedValueAt(hBands,0,1);
   lastBBUpper=GetBufferedValueAt(hBands,1,1);
   lastBBLower=GetBufferedValueAt(hBands,2,1);

   if(InpUseBollinger && lastBBUpper>lastBBLower &&
      lastBBMiddle>0.0)
   {
      double closePrice=iClose(EngineSymbol(),InpTF,1);
      double halfWidth=MathMax(EnginePoint(),(lastBBUpper-lastBBLower)*0.5);
      lastBBPosition=SafeDivide(closePrice-lastBBMiddle,halfWidth);
      double bollingerScore=ClampValue(lastBBPosition,-1.0,1.0);
      double weight=MathMax(0.0,InpBollingerWeight);
      weightedScore+=weight*bollingerScore;
      totalWeight+=weight;
   }
   else
      lastBBPosition=0.0;

   if(totalWeight<=0.0)
      return false;

   lastIndicatorScore=ClampValue(weightedScore/totalWeight,-1.0,1.0);
   return true;
}

int LiveCandleDirection()
{
   int confirmationBars=MathMax(2,MathMin(20,InpDirectionConfirmBars));
   MqlRates candles[];
   ArraySetAsSeries(candles,true);
   if(CopyRates(EngineSymbol(),InpTF,1,confirmationBars,candles)!=confirmationBars)
      return confirmedM1Direction;

   int bullish=0;
   int bearish=0;
   for(int i=0;i<confirmationBars;i++)
   {
      if(candles[i].close>candles[i].open) bullish++;
      else if(candles[i].close<candles[i].open) bearish++;
   }

   lastBullishConfirmCount=bullish;
   lastBearishConfirmCount=bearish;

   int candidateDirection=0;
   if(bullish==confirmationBars) candidateDirection=1;
   else if(bearish==confirmationBars) candidateDirection=-1;

   int majorityDirection=0;
   int majorityNeeded=confirmationBars/2+1;
   if(bullish>=majorityNeeded) majorityDirection=1;
   else if(bearish>=majorityNeeded) majorityDirection=-1;

   int liveDirection=0;
   MqlRates liveCandle[];
   ArraySetAsSeries(liveCandle,true);
   if(CopyRates(EngineSymbol(),InpTF,0,1,liveCandle)==1)
   {
      if(liveCandle[0].close>liveCandle[0].open) liveDirection=1;
      else if(liveCandle[0].close<liveCandle[0].open) liveDirection=-1;
   }

   if(liveDirection==0)
   {
      if(candles[0].close>candles[0].open) liveDirection=1;
      else if(candles[0].close<candles[0].open) liveDirection=-1;
   }

   datetime currentBar=iTime(EngineSymbol(),InpTF,0);
   if(confirmedDirectionStartBar>0 && currentBar>0)
   {
      int held=iBarShift(EngineSymbol(),InpTF,confirmedDirectionStartBar,false);
      lastDirectionHoldBars=held>=0?held:0;
   }

   // Yon karari yalnizca yeni M1 mumunda bir kez degistirilir.
   if(currentBar<=0 || currentBar==lastDirectionEvaluationBar)
      return confirmedM1Direction;

   lastDirectionEvaluationBar=currentBar;

   if(confirmedM1Direction==0)
   {
      int initialDirection=candidateDirection;
      lastDirectionSource=IntegerToString(confirmationBars)+"/"+
                          IntegerToString(confirmationBars)+" GUCLU ONAY";

      if(initialDirection==0)
      {
         initialDirection=majorityDirection;
         int majorityCount=majorityDirection>0?bullish:bearish;
         lastDirectionSource=IntegerToString(majorityCount)+"/"+
                             IntegerToString(confirmationBars)+" COGUNLUK";
      }

      if(initialDirection==0)
      {
         initialDirection=liveDirection;
         lastDirectionSource="CANLI M15 YEDEK SINYAL";
      }

      if(initialDirection!=0)
      {
         confirmedM1Direction=initialDirection;
         confirmedDirectionStartBar=currentBar;
         lastDirectionHoldBars=0;
      }
   }
   else if(candidateDirection!=0 &&
           candidateDirection!=confirmedM1Direction &&
           lastDirectionHoldBars>=MathMax(1,InpMinimumHoldBars))
   {
      confirmedM1Direction=candidateDirection;
      confirmedDirectionStartBar=currentBar;
      lastDirectionHoldBars=0;
      lastDirectionSource=IntegerToString(confirmationBars)+"/"+
                          IntegerToString(confirmationBars)+" TERS YON ONAYI";
   }

   return confirmedM1Direction;
}

int TrendDirection12()
{
   int window=MathMax(2,MathMin(60,InpDirectionWindow));
   int lookback=MathMax(window+2,MathMin(120,InpDirectionLookback));

   MqlRates bars[];
   ArraySetAsSeries(bars,true);
   int needed=lookback+2;
   int copied=CopyRates(EngineSymbol(),InpTF,0,needed,bars);

   lastTrendBuyVotes=0;
   lastTrendSellVotes=0;
   lastTrendStrength=0.0;
   lastBullishConfirmCount=0;
   lastBearishConfirmCount=0;
   gSelectedExtremeQuality=0.0;
   gSelectedExtremeAnchorShift=0;

   if(copied<needed)
      return 0;

   int direction=0;
   int windowBars=0;
   int anchorShift=0;
   double quality=0.0;

   if(!DetectTwelveCandleDirectionSignal(EngineSymbol(),bars,direction,
                                         windowBars,anchorShift,quality))
   {
      gSelectedStreakCount=0;
      return 0;
   }

   gSelectedStreakCount=windowBars;
   gSelectedExtremeQuality=quality;
   gSelectedExtremeAnchorShift=anchorShift;

   // Panel icin 12 mum icindeki yesil/kirmizi sayisini da hesapla.
   for(int i=1;i<=windowBars && i<ArraySize(bars);i++)
   {
      if(bars[i].close>bars[i].open) lastBullishConfirmCount++;
      else if(bars[i].close<bars[i].open) lastBearishConfirmCount++;
   }

   if(direction>0)
      lastTrendBuyVotes=windowBars;
   else
      lastTrendSellVotes=windowBars;

   lastTrendStrength=ClampValue(quality,0.0,1.0);
   return direction;
}

double AverageRange(MqlRates &bars[],int length)
{
   double total=0.0;
   int usable=MathMin(length,ArraySize(bars));

   for(int i=0;i<usable;i++)
      total+=MathMax(EnginePoint(),bars[i].high-bars[i].low);

   return usable>0?total/usable:EnginePoint();
}

double AverageVolume(MqlRates &bars[],int length)
{
   double total=0.0;
   int usable=MathMin(length,ArraySize(bars));

   for(int i=0;i<usable;i++)
      total+=(double)bars[i].tick_volume;

   return usable>0?MathMax(1.0,total/usable):1.0;
}

double HighestHigh(MqlRates &bars[],int length)
{
   double highest=bars[0].high;
   int usable=MathMin(length,ArraySize(bars));

   for(int i=1;i<usable;i++)
      if(bars[i].high>highest)
         highest=bars[i].high;

   return highest;
}

double LowestLow(MqlRates &bars[],int length)
{
   double lowest=bars[0].low;
   int usable=MathMin(length,ArraySize(bars));

   for(int i=1;i<usable;i++)
      if(bars[i].low<lowest)
         lowest=bars[i].low;

   return lowest;
}

double StrategyFamilyValue(MqlRates &bars[],int family,int length)
{
   int usable=MathMin(length,ArraySize(bars)-1);
   if(usable<1)
      return 0.0;

   double averageRange=MathMax(EnginePoint(),AverageRange(bars,usable));
   double value=0.0;

   if(family==0)
   {
      double momentum=bars[0].close-bars[usable].close;
      value=SafeDivide(momentum,averageRange*MathSqrt((double)usable));
   }
   else if(family==1)
   {
      double bodyTotal=0.0;
      double rangeTotal=0.0;
      for(int i=0;i<usable;i++)
      {
         bodyTotal+=bars[i].close-bars[i].open;
         rangeTotal+=MathMax(EnginePoint(),bars[i].high-bars[i].low);
      }
      value=SafeDivide(bodyTotal,rangeTotal);
   }
   else if(family==2)
   {
      double currentRange=MathMax(EnginePoint(),bars[0].high-bars[0].low);
      value=SafeDivide(currentRange,averageRange)-1.0;
   }
   else if(family==3)
   {
      double upper=0.0;
      double ranges=0.0;
      for(int i=0;i<usable;i++)
      {
         upper+=bars[i].high-MathMax(bars[i].open,bars[i].close);
         ranges+=MathMax(EnginePoint(),bars[i].high-bars[i].low);
      }
      value=-SafeDivide(upper,ranges);
   }
   else if(family==4)
   {
      double lower=0.0;
      double ranges=0.0;
      for(int i=0;i<usable;i++)
      {
         lower+=MathMin(bars[i].open,bars[i].close)-bars[i].low;
         ranges+=MathMax(EnginePoint(),bars[i].high-bars[i].low);
      }
      value=SafeDivide(lower,ranges);
   }
   else if(family==5)
   {
      double locationTotal=0.0;
      for(int i=0;i<usable;i++)
      {
         double range=MathMax(EnginePoint(),bars[i].high-bars[i].low);
         locationTotal+=2.0*(bars[i].close-bars[i].low)/range-1.0;
      }
      value=locationTotal/usable;
   }
   else if(family==6)
   {
      double weighted=0.0;
      double weightAbs=0.0;
      for(int i=0;i<usable;i++)
      {
         double weight=(double)(usable-1-2*i);
         weighted+=weight*bars[i].close;
         weightAbs+=MathAbs(weight);
      }
      value=SafeDivide(weighted,MathMax(1.0,weightAbs)*averageRange);
   }
   else if(family==7)
   {
      int half=MathMax(1,usable/2);
      double recent=AverageRange(bars,half);
      double full=AverageRange(bars,usable);
      value=SafeDivide(recent,MathMax(EnginePoint(),full))-1.0;
   }
   else if(family==8)
   {
      double highest=HighestHigh(bars,usable);
      double lowest=LowestLow(bars,usable);
      value=2.0*SafeDivide(bars[0].close-lowest,
                           MathMax(EnginePoint(),highest-lowest))-1.0;
   }
   else if(family==9)
   {
      double averageVolume=AverageVolume(bars,usable);
      double currentVolume=(double)bars[0].tick_volume;
      double direction=0.0;
      if(bars[0].close>bars[0].open) direction=1.0;
      else if(bars[0].close<bars[0].open) direction=-1.0;
      value=direction*(SafeDivide(currentVolume,averageVolume)-1.0);
   }
   else if(family==10)
   {
      // Fiyat ivmesi: yakın dönem hareketi ile önceki hareketin farkı.
      int half=MathMax(1,usable/2);
      double recentMove=bars[0].close-bars[half].close;
      double previousMove=bars[half].close-bars[usable].close;
      value=SafeDivide(recentMove-previousMove,
                       averageRange*MathSqrt((double)usable));
   }
   else if(family==11)
   {
      // Trend verimliliği: net hareket / toplam fiyat yolu.
      double netMove=bars[0].close-bars[usable].close;
      double totalPath=0.0;
      for(int i=0;i<usable;i++)
         totalPath+=MathAbs(bars[i].close-bars[i+1].close);
      value=SafeDivide(netMove,MathMax(EnginePoint(),totalPath));
   }
   else if(family==12)
   {
      // RSI dengesi: yukari ve asagi kapanis hareketlerinin orani.
      double gains=0.0;
      double losses=0.0;
      for(int i=0;i<usable;i++)
      {
         double change=bars[i].close-bars[i+1].close;
         if(change>0.0) gains+=change;
         else losses-=change;
      }
      double rsiBalance=SafeDivide(gains-losses,
                                   MathMax(EnginePoint(),gains+losses));
      value=rsiBalance;
   }
   else if(family==13)
   {
      // Getiri otokorelasyonu: hareketin devam veya donus egilimi.
      double meanReturn=0.0;
      for(int i=0;i<usable;i++)
         meanReturn+=bars[i].close-bars[i+1].close;
      meanReturn/=usable;

      double covariance=0.0;
      double variance=0.0;
      for(int i=0;i<usable-1;i++)
      {
         double first=(bars[i].close-bars[i+1].close)-meanReturn;
         double second=(bars[i+1].close-bars[i+2].close)-meanReturn;
         covariance+=first*second;
         variance+=first*first;
      }
      value=SafeDivide(covariance,MathMax(EnginePoint()*EnginePoint(),variance));
   }
   else if(family==14)
   {
      // Kapanis z-skoru: fiyat ortalamadan ne kadar uzak.
      double meanClose=0.0;
      for(int i=0;i<usable;i++)
         meanClose+=bars[i].close;
      meanClose/=usable;

      double variance=0.0;
      for(int i=0;i<usable;i++)
      {
         double delta=bars[i].close-meanClose;
         variance+=delta*delta;
      }
      variance/=usable;
      value=SafeDivide(bars[0].close-meanClose,
                       MathMax(EnginePoint(),MathSqrt(variance)));
   }
   else if(family==15)
   {
      // Mum surekliligi: yesil ve kirmizi mumlarin net baskisi.
      double persistence=0.0;
      for(int i=0;i<usable;i++)
      {
         if(bars[i].close>bars[i].open) persistence+=1.0;
         else if(bars[i].close<bars[i].open) persistence-=1.0;
      }
      value=persistence/usable;
   }
   else if(family==16)
   {
      // Gap baskisi: acilis ile onceki kapanis arasindaki net bosluk.
      double gapTotal=0.0;
      double rangeTotal=0.0;
      for(int i=0;i<usable;i++)
      {
         gapTotal+=bars[i].open-bars[i+1].close;
         rangeTotal+=MathMax(EnginePoint(),bars[i].high-bars[i].low);
      }
      value=SafeDivide(gapTotal,rangeTotal);
   }
   else if(family==17)
   {
      // Yukari/asagi volatilite dengesi.
      double upVariance=0.0;
      double downVariance=0.0;
      for(int i=0;i<usable;i++)
      {
         double change=bars[i].close-bars[i+1].close;
         if(change>0.0) upVariance+=change*change;
         else downVariance+=change*change;
      }
      double upVol=MathSqrt(upVariance);
      double downVol=MathSqrt(downVariance);
      value=SafeDivide(upVol-downVol,
                       MathMax(EnginePoint(),upVol+downVol));
   }
   else if(family==18)
   {
      // Hacim agirlikli ortalama fiyata gore trend.
      double weightedPrice=0.0;
      double totalVolume=0.0;
      for(int i=0;i<usable;i++)
      {
         double volume=MathMax(1.0,(double)bars[i].tick_volume);
         double typical=(bars[i].high+bars[i].low+bars[i].close)/3.0;
         weightedPrice+=typical*volume;
         totalVolume+=volume;
      }
      double vwap=SafeDivide(weightedPrice,totalVolume);
      value=SafeDivide(bars[0].close-vwap,averageRange);
   }
   else if(family==19)
   {
      // Hacim ivmesi ile mum yonunun ortak baskisi.
      int half=MathMax(1,usable/2);
      double recentVolume=AverageVolume(bars,half);
      double fullVolume=AverageVolume(bars,usable);
      double direction=SafeDivide(bars[0].close-bars[usable].close,
                                  averageRange*MathSqrt((double)usable));
      value=direction*(SafeDivide(recentVolume,fullVolume)-1.0);
   }
   else if(family==20)
   {
      // Mum yonu ile genislik agirlikli baski.
      double signedRange=0.0;
      double totalRange=0.0;
      for(int i=0;i<usable;i++)
      {
         double range=MathMax(EnginePoint(),bars[i].high-bars[i].low);
         double direction=0.0;
         if(bars[i].close>bars[i].open) direction=1.0;
         else if(bars[i].close<bars[i].open) direction=-1.0;
         signedRange+=direction*range;
         totalRange+=range;
      }
      value=SafeDivide(signedRange,totalRange);
   }
   else if(family==21)
   {
      // Alt ve ust fitil dengesinden donus baskisi.
      double wickBalance=0.0;
      double totalRange=0.0;
      for(int i=0;i<usable;i++)
      {
         double upper=bars[i].high-MathMax(bars[i].open,bars[i].close);
         double lower=MathMin(bars[i].open,bars[i].close)-bars[i].low;
         wickBalance+=lower-upper;
         totalRange+=MathMax(EnginePoint(),bars[i].high-bars[i].low);
      }
      value=SafeDivide(wickBalance,totalRange);
   }
   else if(family==22)
   {
      // Onceki kanal disina tasma gucu.
      int channelLength=MathMax(2,usable);
      double priorHigh=bars[1].high;
      double priorLow=bars[1].low;
      for(int i=2;i<=channelLength;i++)
      {
         if(bars[i].high>priorHigh) priorHigh=bars[i].high;
         if(bars[i].low<priorLow) priorLow=bars[i].low;
      }
      if(bars[0].close>priorHigh)
         value=SafeDivide(bars[0].close-priorHigh,averageRange);
      else if(bars[0].close<priorLow)
         value=-SafeDivide(priorLow-bars[0].close,averageRange);
      else
         value=2.0*SafeDivide(bars[0].close-priorLow,
                              MathMax(EnginePoint(),priorHigh-priorLow))-1.0;
   }
   else if(family==23)
   {
      // Yon entropisi: duzenli mum serilerine daha guclu oy.
      int upCount=0;
      int downCount=0;
      for(int i=0;i<usable;i++)
      {
         if(bars[i].close>bars[i].open) upCount++;
         else if(bars[i].close<bars[i].open) downCount++;
      }
      int directional=MathMax(1,upCount+downCount);
      double pUp=(double)upCount/directional;
      double pDown=(double)downCount/directional;
      double entropy=0.0;
      if(pUp>0.0) entropy-=pUp*MathLog(pUp)/MathLog(2.0);
      if(pDown>0.0) entropy-=pDown*MathLog(pDown)/MathLog(2.0);
      double directionBalance=(double)(upCount-downCount)/directional;
      value=directionBalance*(1.0-ClampValue(entropy,0.0,1.0));
   }
   else if(family==24)
   {
      // Ortalama donus stratejisi: asiri uzaklasmanin tersine oy.
      double meanClose=0.0;
      for(int i=1;i<=usable;i++)
         meanClose+=bars[i].close;
      meanClose/=usable;
      value=-SafeDivide(bars[0].close-meanClose,
                        averageRange*MathSqrt((double)usable));
   }
   else if(family==25)
   {
      // Yol verimliligi ve yon: puruzsuz trend daha guclu oy verir.
      double netMove=bars[0].close-bars[usable].close;
      double squaredPath=0.0;
      for(int i=0;i<usable;i++)
      {
         double change=bars[i].close-bars[i+1].close;
         squaredPath+=change*change;
      }
      value=SafeDivide(netMove,
                       MathMax(EnginePoint(),MathSqrt(squaredPath*(double)usable)));
   }
   else if(family==26)
   {
      // Gercek aralikla normalize edilmis fiyat baskisi.
      double trueRangeTotal=0.0;
      for(int i=0;i<usable;i++)
      {
         double range1=bars[i].high-bars[i].low;
         double range2=MathAbs(bars[i].high-bars[i+1].close);
         double range3=MathAbs(bars[i].low-bars[i+1].close);
         trueRangeTotal+=MathMax(range1,MathMax(range2,range3));
      }
      double averageTrueRange=MathMax(EnginePoint(),trueRangeTotal/usable);
      value=SafeDivide(bars[0].close-bars[usable].close,
                       averageTrueRange*MathSqrt((double)usable));
   }
   else if(family==27)
   {
      // En yeni ardisik mum serisinin yonu ve uzunlugu.
      int firstDirection=0;
      if(bars[0].close>bars[0].open) firstDirection=1;
      else if(bars[0].close<bars[0].open) firstDirection=-1;

      int streak=0;
      for(int i=0;i<usable;i++)
      {
         int direction=0;
         if(bars[i].close>bars[i].open) direction=1;
         else if(bars[i].close<bars[i].open) direction=-1;
         if(direction==0 || direction!=firstDirection) break;
         streak++;
      }
      value=firstDirection*SafeDivide((double)streak,
                                      MathSqrt((double)usable));
   }
   else if(family==28)
   {
      // Tipik fiyat momentumu.
      double currentTypical=(bars[0].high+bars[0].low+bars[0].close)/3.0;
      double oldTypical=(bars[usable].high+bars[usable].low+
                         bars[usable].close)/3.0;
      value=SafeDivide(currentTypical-oldTypical,
                       averageRange*MathSqrt((double)usable));
   }
   else if(family==29)
   {
      // Kapanisin gecmis dagilimindaki yuzdelik sirasi.
      int below=0;
      int above=0;
      for(int i=1;i<=usable;i++)
      {
         if(bars[i].close<bars[0].close) below++;
         else if(bars[i].close>bars[0].close) above++;
      }
      value=SafeDivide((double)(below-above),(double)usable);
   }

   return ClampValue(value,-5.0,5.0);
}

double StrategyVariant(double rawValue,int variant)
{
   double bounded=MathTanh(rawValue);

   if(variant==0)
      return bounded;

   if(variant==1)
      return MathTanh(rawValue*1.50);

   if(variant==2)
      return MathTanh(rawValue*0.75);

   if(variant==3)
      return bounded>=0.0?bounded*bounded:-bounded*bounded;

   double root=MathSqrt(MathAbs(bounded));
   return bounded>=0.0?root:-root;
}

bool Build3000Strategies()
{
   int horizons[20]={1,2,3,4,5,6,8,10,13,16,
                     21,26,34,42,55,68,89,110,144,180};
   MqlRates bars[];
   ArraySetAsSeries(bars,true);

   int copied=CopyRates(EngineSymbol(),InpTF,1,220,bars);
   if(copied<200)
   {
      lastStrategyCount=0;
      lastStrategyScore=0.0;
      lastAgreement=0.0;
      lastStatus="3000 STRATEJI ICIN M15 TARIHCESI BEKLENIYOR";
      return false;
   }

   ArrayResize(strategyVotes,STRATEGY_COUNT);

   int index=0;
   double sum=0.0;
   int positive=0;
   int negative=0;

   for(int family=0;family<STRATEGY_FAMILIES;family++)
   {
      for(int horizon=0;horizon<STRATEGY_HORIZONS;horizon++)
      {
         double rawValue=StrategyFamilyValue(bars,family,horizons[horizon]);

         for(int variant=0;variant<STRATEGY_VARIANTS;variant++)
         {
            double vote=StrategyVariant(rawValue,variant);
            if(!MathIsValidNumber(vote))
               vote=0.0;

            strategyVotes[index]=vote;
            sum+=vote;

            if(vote>0.0) positive++;
            else if(vote<0.0) negative++;

            index++;
         }
      }
   }

   lastStrategyCount=index;
   lastStrategyScore=ClampValue(sum/STRATEGY_COUNT,-1.0,1.0);
   lastAgreement=(double)MathMax(positive,negative)/STRATEGY_COUNT;

   return index==STRATEGY_COUNT;
}

int DirectionFromValue(double value,double threshold)
{
   if(value>=threshold) return 1;
   if(value<=-threshold) return -1;
   return 0;
}

int ClosedTimeframeDirection(ENUM_TIMEFRAMES timeframe)
{
   MqlRates candle[1];
   if(CopyRates(EngineSymbol(),timeframe,1,1,candle)!=1)
      return 0;

   if(candle[0].close>candle[0].open) return 1;
   if(candle[0].close<candle[0].open) return -1;
   return 0;
}

double DirectCategoryScore(MqlRates &bars[],int category,int horizon,
                           int liveDirection,double fast,double slow,
                           double rsi,double multiTimeframeScore)
{
   int usable=MathMin(horizon,ArraySize(bars)-2);
   if(usable<1)
      return 0.0;

   double averageRange=MathMax(EnginePoint(),AverageRange(bars,usable));
   double currentRange=MathMax(EnginePoint(),bars[0].high-bars[0].low);
   double currentBody=SafeDivide(bars[0].close-bars[0].open,currentRange);
   double momentum=SafeDivide(bars[0].close-bars[usable].close,
                              averageRange*MathSqrt((double)usable));

   double path=0.0;
   double bodyPressure=0.0;
   double rangeTotal=0.0;
   double volumeTotal=0.0;
   int upCount=0;
   int downCount=0;

   for(int i=0;i<usable;i++)
   {
      double change=bars[i].close-bars[i+1].close;
      double range=MathMax(EnginePoint(),bars[i].high-bars[i].low);
      path+=MathAbs(change);
      bodyPressure+=bars[i].close-bars[i].open;
      rangeTotal+=range;
      volumeTotal+=(double)bars[i].tick_volume;
      if(bars[i].close>bars[i].open) upCount++;
      else if(bars[i].close<bars[i].open) downCount++;
   }

   double efficiency=SafeDivide(bars[0].close-bars[usable].close,
                                MathMax(EnginePoint(),path));
   double persistence=SafeDivide((double)(upCount-downCount),(double)usable);

   double meanClose=0.0;
   for(int i=0;i<usable;i++)
      meanClose+=bars[i].close;
   meanClose/=usable;

   double variance=0.0;
   for(int i=0;i<usable;i++)
   {
      double delta=bars[i].close-meanClose;
      variance+=delta*delta;
   }
   variance/=usable;
   double standardDeviation=MathMax(EnginePoint(),MathSqrt(variance));
   double zScore=SafeDivide(bars[0].close-meanClose,standardDeviation);

   double priorHigh=bars[1].high;
   double priorLow=bars[1].low;
   for(int i=2;i<=usable;i++)
   {
      if(bars[i].high>priorHigh) priorHigh=bars[i].high;
      if(bars[i].low<priorLow) priorLow=bars[i].low;
   }
   double channelWidth=MathMax(EnginePoint(),priorHigh-priorLow);
   double channelPosition=2.0*SafeDivide(bars[0].close-priorLow,
                                        channelWidth)-1.0;

   double breakoutScore=0.0;
   if(bars[0].close>priorHigh)
      breakoutScore=1.0+SafeDivide(bars[0].close-priorHigh,averageRange);
   else if(bars[0].close<priorLow)
      breakoutScore=-1.0-SafeDivide(priorLow-bars[0].close,averageRange);
   else
      breakoutScore=channelPosition*0.25;

   double upperWick=bars[0].high-MathMax(bars[0].open,bars[0].close);
   double lowerWick=MathMin(bars[0].open,bars[0].close)-bars[0].low;
   double wickBalance=SafeDivide(lowerWick-upperWick,currentRange);

   double averageVolume=MathMax(1.0,SafeDivide(volumeTotal,(double)usable));
   double volumeRatio=SafeDivide((double)bars[0].tick_volume,averageVolume)-1.0;
   double candleDirection=0.0;
   if(bars[0].close>bars[0].open) candleDirection=1.0;
   else if(bars[0].close<bars[0].open) candleDirection=-1.0;

   double recentMove=bars[0].close-bars[MathMax(1,usable/2)].close;
   double olderMove=bars[MathMax(1,usable/2)].close-bars[usable].close;
   double macdProxy=SafeDivide(recentMove-olderMove,
                               averageRange*MathSqrt((double)usable));

   double emaScore=SafeDivide(fast-slow,averageRange)+
                   0.25*SafeDivide(bars[0].close-fast,averageRange);
   double rsiScore=(rsi-50.0)/25.0;
   double stochScore=2.0*SafeDivide(bars[0].close-priorLow,channelWidth)-1.0;
   double trendStrength=MathAbs(efficiency);
   double adxProxy=(momentum>=0.0?1.0:-1.0)*trendStrength*2.0;
   double volatilityRatio=SafeDivide(currentRange,averageRange)-1.0;

   int fastLength=MathMax(1,MathMin(9,usable));
   int slowLength=MathMax(1,MathMin(26,usable));
   double fastHigh=bars[0].high;
   double fastLow=bars[0].low;
   double slowHigh=bars[0].high;
   double slowLow=bars[0].low;
   for(int i=1;i<slowLength;i++)
   {
      if(bars[i].high>slowHigh) slowHigh=bars[i].high;
      if(bars[i].low<slowLow) slowLow=bars[i].low;
      if(i<fastLength)
      {
         if(bars[i].high>fastHigh) fastHigh=bars[i].high;
         if(bars[i].low<fastLow) fastLow=bars[i].low;
      }
   }
   double fastMid=(fastHigh+fastLow)/2.0;
   double slowMid=(slowHigh+slowLow)/2.0;
   double cloudScore=SafeDivide(fastMid-slowMid,averageRange)+
                     0.25*SafeDivide(bars[0].close-slowMid,averageRange);

   double smartMoneyScore=wickBalance*0.50;
   if(bars[0].low<priorLow && bars[0].close>priorLow)
      smartMoneyScore=1.0+SafeDivide(priorLow-bars[0].low,averageRange);
   else if(bars[0].high>priorHigh && bars[0].close<priorHigh)
      smartMoneyScore=-1.0-SafeDivide(bars[0].high-priorHigh,averageRange);

   double score=0.0;

   if(category==0)
      score=0.45*currentBody+0.30*persistence+0.25*liveDirection;
   else if(category==1)
      score=0.60*momentum+0.40*efficiency;
   else if(category==2)
      score=emaScore;
   else if(category==3)
      score=0.75*rsiScore+0.25*momentum;
   else if(category==4)
      score=macdProxy;
   else if(category==5)
      score=0.65*zScore+0.35*volatilityRatio*currentBody;
   else if(category==6)
      score=stochScore;
   else if(category==7)
      score=adxProxy;
   else if(category==8)
      score=momentum*(1.0+ClampValue(volatilityRatio,-0.5,1.5));
   else if(category==9)
      score=-channelPosition+0.25*wickBalance;
   else if(category==10)
      score=breakoutScore;
   else if(category==11)
      score=0.60*currentBody+0.40*wickBalance;
   else if(category==12)
      score=candleDirection*volumeRatio+0.25*momentum;
   else if(category==13)
      score=cloudScore;
   else if(category==14)
      score=-zScore;
   else if(category==15)
      score=smartMoneyScore;
   else if(category==16)
      score=multiTimeframeScore;
   else if(category==17)
      score=0.20*momentum+0.15*emaScore+0.15*rsiScore+
            0.15*macdProxy+0.15*multiTimeframeScore+
            0.10*currentBody+0.10*breakoutScore;

   return ClampValue(score,-5.0,5.0);
}

int DirectRuleVote(double baseScore,int style,int thresholdIndex,
                   double candleScore,double trendScore,
                   double breakoutScore,double volumeScore,
                   double multiTimeframeScore)
{
   double thresholds[10]={0.03,0.05,0.08,0.11,0.14,
                          0.18,0.23,0.29,0.36,0.45};
   double threshold=thresholds[MathMax(0,MathMin(9,thresholdIndex))];
   double adjusted=baseScore;

   if(style==1)
   {
      adjusted=0.75*baseScore+0.25*candleScore;
      if(baseScore*candleScore<0.0 && MathAbs(baseScore)<threshold*2.0)
         return 0;
   }
   else if(style==2)
   {
      adjusted=0.70*baseScore+0.30*trendScore;
      if(baseScore*trendScore<0.0 && MathAbs(baseScore)<threshold*2.0)
         return 0;
   }
   else if(style==3)
   {
      adjusted=0.60*baseScore+0.25*breakoutScore+0.15*volumeScore;
   }
   else if(style==4)
   {
      adjusted=0.55*baseScore+0.15*candleScore+0.15*trendScore+
               0.15*multiTimeframeScore;
   }

   return DirectionFromValue(adjusted,threshold);
}

bool Build900DirectStrategies(double fast,double slow,double rsi,
                              int liveDirection)
{
   int horizons[10]={1,2,3,5,8,13,21,34,55,89};
   MqlRates bars[];
   ArraySetAsSeries(bars,true);

   int copied=CopyRates(EngineSymbol(),InpTF,1,220,bars);
   if(copied<120)
   {
      lastDirectCount=0;
      lastDirectBuyVotes=0;
      lastDirectSellVotes=0;
      lastDirectNeutralVotes=0;
      lastDirectScore=0.0;
      lastDirectAgreement=0.0;
      lastStatus="900 DIREKT STRATEJI ICIN TARIHCE BEKLENIYOR";
      return false;
   }

   int mtfM5=ClosedTimeframeDirection(PERIOD_M5);
   int mtfM15=ClosedTimeframeDirection(PERIOD_M15);
   int mtfH1=ClosedTimeframeDirection(PERIOD_H1);
   int mtfH4=ClosedTimeframeDirection(PERIOD_H4);
   int mtfD1=ClosedTimeframeDirection(PERIOD_D1);
   double multiTimeframeScore=(mtfM5+mtfM15+mtfH1+mtfH4+mtfD1)/5.0;

   double categoryScores[180];
   for(int category=0;category<DIRECT_CATEGORIES;category++)
   {
      for(int horizonIndex=0;horizonIndex<10;horizonIndex++)
      {
         categoryScores[category*10+horizonIndex]=
            DirectCategoryScore(bars,category,horizons[horizonIndex],
                                liveDirection,fast,slow,rsi,
                                multiTimeframeScore);
      }
   }

   ArrayResize(directStrategyVotes,DIRECT_STRATEGY_COUNT);
   int index=0;
   int buyVotes=0;
   int sellVotes=0;
   int neutralVotes=0;

   for(int category=0;category<DIRECT_CATEGORIES;category++)
   {
      for(int rule=0;rule<DIRECT_RULES_PER_CATEGORY;rule++)
      {
         int horizonIndex=rule%10;
         int style=rule/10;
         double baseScore=categoryScores[category*10+horizonIndex];
         double candleScore=categoryScores[horizonIndex];
         double trendScore=categoryScores[10+horizonIndex];
         double breakoutScore=categoryScores[100+horizonIndex];
         double volumeScore=categoryScores[120+horizonIndex];

         int vote=DirectRuleVote(baseScore,style,horizonIndex,
                                 candleScore,trendScore,breakoutScore,
                                 volumeScore,multiTimeframeScore);

         directStrategyVotes[index]=(double)vote;
         if(vote>0) buyVotes++;
         else if(vote<0) sellVotes++;
         else neutralVotes++;
         index++;
      }
   }

   lastDirectCount=index;
   lastDirectBuyVotes=buyVotes;
   lastDirectSellVotes=sellVotes;
   lastDirectNeutralVotes=neutralVotes;

   int activeVotes=buyVotes+sellVotes;
   if(activeVotes>0)
   {
      lastDirectScore=(double)(buyVotes-sellVotes)/activeVotes;
      lastDirectAgreement=(double)MathMax(buyVotes,sellVotes)/activeVotes;
   }
   else
   {
      lastDirectScore=0.0;
      lastDirectAgreement=0.0;
   }

   return index==DIRECT_STRATEGY_COUNT;
}

double AdvancedRegressionSlope(MqlRates &bars[],int length,double &rSquared)
{
   rSquared=0.0;
   if(length<3 || ArraySize(bars)<length)
      return 0.0;

   double sumX=0.0;
   double sumY=0.0;
   double sumXY=0.0;
   double sumXX=0.0;

   for(int i=0;i<length;i++)
   {
      double x=(double)i;
      double y=bars[length-1-i].close;
      sumX+=x;
      sumY+=y;
      sumXY+=x*y;
      sumXX+=x*x;
   }

   double denominator=length*sumXX-sumX*sumX;
   if(MathAbs(denominator)<1e-12)
      return 0.0;

   double slope=(length*sumXY-sumX*sumY)/denominator;
   double intercept=(sumY-slope*sumX)/length;
   double mean=sumY/length;
   double totalVariance=0.0;
   double residualVariance=0.0;

   for(int i=0;i<length;i++)
   {
      double x=(double)i;
      double y=bars[length-1-i].close;
      double fitted=intercept+slope*x;
      totalVariance+=(y-mean)*(y-mean);
      residualVariance+=(y-fitted)*(y-fitted);
   }

   if(totalVariance>1e-12)
      rSquared=ClampValue(1.0-residualVariance/totalVariance,0.0,1.0);

   return slope;
}

bool Build100AdvancedStrategies()
{
   MqlRates bars[];
   ArraySetAsSeries(bars,true);
   int copied=CopyRates(EngineSymbol(),InpTF,1,260,bars);

   if(copied<150)
   {
      lastAdvancedScore=0.0;
      lastAdvancedAgreement=0.0;
      lastAdvancedBuyVotes=0;
      lastAdvancedSellVotes=0;
      lastAdvancedNeutralVotes=0;
      return false;
   }

   double averageRange=MathMax(EnginePoint(),AverageRange(bars,20));
   double currentRange=MathMax(EnginePoint(),bars[0].high-bars[0].low);
   double momentum1=SafeDivide(bars[0].close-bars[1].close,averageRange);
   double momentum3=SafeDivide(bars[0].close-bars[3].close,averageRange);
   double momentum5=SafeDivide(bars[0].close-bars[5].close,averageRange);
   double momentum10=SafeDivide(bars[0].close-bars[10].close,averageRange);
   double momentum30=SafeDivide(bars[0].close-bars[30].close,
                                averageRange*MathSqrt(30.0));
   double velocityNow=SafeDivide(bars[0].close-bars[1].close,averageRange);
   double velocityPrevious=SafeDivide(bars[1].close-bars[2].close,averageRange);
   double acceleration=velocityNow-velocityPrevious;
   double priorAcceleration=velocityPrevious-
      SafeDivide(bars[2].close-bars[3].close,averageRange);
   double accelerationReversal=acceleration-priorAcceleration;
   double persistence=AIPersistence(bars,0,10);

   double bodyScore=SafeDivide(bars[0].close-bars[0].open,currentRange);
   double upperWick=bars[0].high-MathMax(bars[0].open,bars[0].close);
   double lowerWick=MathMin(bars[0].open,bars[0].close)-bars[0].low;
   double wickRejection=SafeDivide(lowerWick-upperWick,currentRange);
   double recentRange=AverageRange(bars,5);
   double olderRange=0.0;
   for(int i=5;i<25;i++)
      olderRange+=MathMax(EnginePoint(),bars[i].high-bars[i].low);
   olderRange=MathMax(EnginePoint(),olderRange/20.0);
   double compression=ClampValue((olderRange-recentRange)/olderRange,-1.0,1.0);
   double expansion=ClampValue((currentRange-recentRange)/averageRange,-2.0,2.0);

   double priorHigh=bars[1].high;
   double priorLow=bars[1].low;
   for(int i=2;i<=20;i++)
   {
      if(bars[i].high>priorHigh) priorHigh=bars[i].high;
      if(bars[i].low<priorLow) priorLow=bars[i].low;
   }
   double breakoutScore=0.0;
   if(bars[0].close>priorHigh)
      breakoutScore=1.0+SafeDivide(bars[0].close-priorHigh,averageRange);
   else if(bars[0].close<priorLow)
      breakoutScore=-1.0-SafeDivide(priorLow-bars[0].close,averageRange);
   else
      breakoutScore=2.0*SafeDivide(bars[0].close-priorLow,
                                  MathMax(EnginePoint(),priorHigh-priorLow))-1.0;

   double rSquared10=0.0;
   double rSquared30=0.0;
   double regression10=SafeDivide(AdvancedRegressionSlope(bars,10,rSquared10),
                                  averageRange);
   double regression30=SafeDivide(AdvancedRegressionSlope(bars,30,rSquared30),
                                  averageRange);
   double curvature=regression10-regression30;
   double trendQuality=(rSquared10+rSquared30)*0.5;

   double recentHigh=bars[0].high;
   double recentLow=bars[0].low;
   double olderHigh=bars[6].high;
   double olderLow=bars[6].low;
   for(int i=1;i<6;i++)
   {
      if(bars[i].high>recentHigh) recentHigh=bars[i].high;
      if(bars[i].low<recentLow) recentLow=bars[i].low;
   }
   for(int i=7;i<13;i++)
   {
      if(bars[i].high>olderHigh) olderHigh=bars[i].high;
      if(bars[i].low<olderLow) olderLow=bars[i].low;
   }
   double structureScore=SafeDivide((recentHigh-olderHigh)+
                                    (recentLow-olderLow),2.0*averageRange);
   double fractalScore=0.55*structureScore+0.45*breakoutScore;

   double swingNow=SafeDivide(bars[0].close-bars[5].close,averageRange);
   double swingPrevious=SafeDivide(bars[5].close-bars[10].close,averageRange);
   double swingAsymmetry=swingNow-0.70*swingPrevious;
   double high34=bars[0].high;
   double low34=bars[0].low;
   for(int i=1;i<34;i++)
   {
      if(bars[i].high>high34) high34=bars[i].high;
      if(bars[i].low<low34) low34=bars[i].low;
   }
   double rangePosition=2.0*SafeDivide(bars[0].close-low34,
                                      MathMax(EnginePoint(),high34-low34))-1.0;
   double trendSign=regression30>=0.0?1.0:-1.0;
   double pullbackQuality=trendSign*(1.0-MathAbs(rangePosition));

   double mean20=0.0;
   for(int i=0;i<20;i++) mean20+=bars[i].close;
   mean20/=20.0;
   double timeAtPrice=0.0;
   for(int i=0;i<12;i++)
      timeAtPrice+=bars[i].close>=mean20?1.0:-1.0;
   timeAtPrice/=12.0;

   MqlDateTime serverPart;
   TimeToStruct(BrokerServerTime(),serverPart);
   bool activeSession=serverPart.hour>=7 && serverPart.hour<=18;
   double sessionImpulse=(activeSession?1.0:0.60)*momentum3;

   double spreadQuality=1.0;
   if(lastCurrentSpread>0 && lastMinimumSpread>=0)
      spreadQuality=ClampValue((double)(lastMinimumSpread+1)/
                               (lastCurrentSpread+1),0.0,1.0);
   double spreadAdjustedMomentum=momentum3*spreadQuality;
   double executionQuality=1.0/(1.0+averageExecutionSlippage/10.0);
   double tickScore=lastTickImbalance;

   double categoryScore[10];
   categoryScore[0]=0.35*momentum3+0.30*acceleration+
                    0.20*accelerationReversal+0.15*persistence;
   categoryScore[1]=0.45*bodyScore+0.35*wickRejection+
                    0.20*expansion;
   categoryScore[2]=0.50*breakoutScore+0.30*compression*breakoutScore+
                    0.20*expansion*bodyScore;
   categoryScore[3]=trendQuality*(0.60*regression10+0.40*regression30)+
                    (1.0-trendQuality)*(-rangePosition)*0.40;
   categoryScore[4]=0.55*curvature+0.30*regression10+
                    0.15*acceleration;
   categoryScore[5]=0.55*fractalScore+0.45*structureScore;
   categoryScore[6]=0.45*structureScore+0.30*momentum30+
                    0.25*persistence;
   categoryScore[7]=0.55*swingAsymmetry+0.25*pullbackQuality+
                    0.20*momentum5;
   categoryScore[8]=0.40*timeAtPrice+0.35*sessionImpulse+
                    0.25*breakoutScore;
   categoryScore[9]=spreadQuality*executionQuality*
                    (0.50*spreadAdjustedMomentum+0.50*tickScore);

   ArrayResize(advancedStrategyVotes,ADVANCED_STRATEGY_COUNT);
   int index=0;
   int buyVotes=0;
   int sellVotes=0;
   int neutralVotes=0;

   for(int category=0;category<10;category++)
   {
      for(int variant=0;variant<10;variant++)
      {
         double score=categoryScore[category];
         double threshold=0.05+0.025*variant;

         if(variant==1) score=0.75*score+0.25*momentum1;
         else if(variant==2) score=0.70*score+0.30*momentum5;
         else if(variant==3) score=0.70*score+0.30*momentum10;
         else if(variant==4) score=0.65*score+0.35*bodyScore;
         else if(variant==5) score=0.65*score+0.35*breakoutScore;
         else if(variant==6) score=0.65*score+0.35*structureScore;
         else if(variant==7) score=0.65*score+0.35*regression10;
         else if(variant==8) score=0.60*score+0.25*tickScore+
                                           0.15*spreadAdjustedMomentum;
         else if(variant==9)
         {
            score=0.55*score+0.20*momentum30+0.15*persistence+
                  0.10*lastIndicatorScore;
            threshold+=0.05;
         }

         int vote=DirectionFromValue(score,threshold);
         advancedStrategyVotes[index]=(double)vote;
         if(vote>0) buyVotes++;
         else if(vote<0) sellVotes++;
         else neutralVotes++;
         index++;
      }
   }

   lastAdvancedBuyVotes=buyVotes;
   lastAdvancedSellVotes=sellVotes;
   lastAdvancedNeutralVotes=neutralVotes;
   int activeVotes=buyVotes+sellVotes;

   if(activeVotes>0)
   {
      lastAdvancedScore=(double)(buyVotes-sellVotes)/activeVotes;
      lastAdvancedAgreement=(double)MathMax(buyVotes,sellVotes)/activeVotes;
   }
   else
   {
      lastAdvancedScore=0.0;
      lastAdvancedAgreement=0.0;
   }

   return index==ADVANCED_STRATEGY_COUNT;
}

double AISigmoid(double value)
{
   value=ClampValue(value,-30.0,30.0);
   return 1.0/(1.0+MathExp(-value));
}

double AIClipGradient(double value)
{
   double limit=MathMax(0.10,AI_Gradient_Kirpma);
   return ClampValue(value,-limit,limit);
}

double AISmoothTarget(double target)
{
   double smoothing=ClampValue(AI_Etiket_Yumusatma,0.0,0.20);
   target=ClampValue(target,0.0,1.0);
   return smoothing+(1.0-2.0*smoothing)*target;
}

double AIOneStepSoftTarget(double newerClose,double olderClose,double scale)
{
   scale=MathMax(EnginePoint(),scale);
   double normalized=(newerClose-olderClose)/scale;
   double minimumMove=MathMax(0.0,AI_Min_Hareket_ATR);
   if(MathAbs(normalized)<minimumMove)
      normalized*=0.50;
   return ClampValue(AISigmoid(2.20*normalized),0.02,0.98);
}

double AIMultiHorizonTarget(MqlRates &bars[],int offset)
{
   if(offset<1 || offset>=ArraySize(bars))
      return 0.50;

   double localRange=0.0;
   int rangeCount=0;
   int rangeEnd=MathMin(ArraySize(bars)-1,offset+24);
   for(int i=offset;i<=rangeEnd;i++)
   {
      localRange+=MathMax(EnginePoint(),bars[i].high-bars[i].low);
      rangeCount++;
   }
   localRange=rangeCount>0?localRange/rangeCount:EnginePoint();

   double weightedMove=0.0;
   double weightTotal=0.0;
   double absTotal=0.0;
   int positive=0;
   int negative=0;

   for(int horizon=1;horizon<=AI_MULTI_HORIZONS;horizon++)
   {
      int futureIndex=offset-horizon;
      if(futureIndex<0) continue;

      double move=bars[futureIndex].close-bars[offset].close;
      double scale=MathMax(EnginePoint(),localRange*MathSqrt((double)horizon));
      double normalized=MathTanh(move/scale);
      double weight=1.0/MathSqrt((double)horizon);

      // Uzun ufuklarin trend bilgisini kaybetme, kisa ufuklari da tamamen ezme.
      if(horizon>=12)  weight*=1.04;
      if(horizon>=24)  weight*=1.07;
      if(horizon>=48)  weight*=1.10;
      if(horizon>=72)  weight*=1.12;
      if(horizon>=96)  weight*=1.14;
      if(horizon>=120) weight*=1.16;
      if(horizon>=160) weight*=1.18;
      if(horizon>=192) weight*=1.20;
      if(horizon>=224) weight*=1.22;

      if(AI_Zamansal_Dikkat)
         weight*=0.70+0.30*MathAbs(normalized);

      weightedMove+=weight*normalized;
      absTotal+=weight*MathAbs(normalized);
      weightTotal+=weight;
      if(move>0.0) positive++;
      else if(move<0.0) negative++;
   }

   if(weightTotal<=0.0) return 0.50;
   int directional=positive+negative;
   double signAgreement=directional>0?
                        (double)MathMax(positive,negative)/directional:0.50;
   double strength=absTotal/weightTotal;
   double score=weightedMove/weightTotal;

   // Hedef, kararsiz rejimde 0.50'ye yaklasir; tutarli rejimde daha belirgin olur.
   double certainty=ClampValue(0.35+0.45*signAgreement+0.20*strength,0.30,1.0);
   return ClampValue(AISigmoid(2.25*score*certainty),0.02,0.98);
}

void InitializeDeepAI()
{
   for(int model=0;model<AI_MODELS;model++)
   {
      for(int i=0;i<AI_HIDDEN_1;i++)
      {
         aiB1[model][i]=0.0;
         for(int j=0;j<AI_INPUTS;j++)
            aiW1[model][i][j]=0.07*MathSin((model+1)*53.117+
                                          (i+1)*12.9898+
                                          (j+1)*78.233);
      }

      for(int k=0;k<AI_HIDDEN_2;k++)
      {
         aiB2[model][k]=0.0;
         aiW3[model][k]=0.07*MathSin((model+1)*29.731+
                                    (k+1)*39.425);
         for(int i=0;i<AI_HIDDEN_1;i++)
            aiW2[model][k][i]=0.07*MathSin((model+1)*43.331+
                                          (k+1)*17.173+
                                          (i+1)*31.719);
      }

      aiB3[model]=0.0;
      aiModelAccuracy[model]=0.50;
      aiModelFastQuality[model]=0.50;
      lastAIModelProbability[model]=0.50;
   }

   for(int network=0;network<AI_MICRO_CAPACITY;network++)
   {
      aiMicroB[network]=0.01*MathSin((network+1)*0.1731);
      aiMicroAccuracy[network]=0.50;
      aiMicroFastQuality[network]=0.50;

      for(int j=0;j<AI_MICRO_INPUTS;j++)
         aiMicroW[network][j]=0.10*MathSin((network+1)*0.731+
                                          (j+1)*2.173+
                                          (network%17)*0.119);
   }

   aiHasPendingSample=false;
   aiLastSampleBar=0;
   aiTrainingCount=0;
   lastAIProbability=0.50;
   lastAIScore=0.0;
   lastAIConfidence=0.50;
   lastAILoss=0.0;
   lastAIDisagreement=0.0;
   lastAIConsensus=0.50;
   lastAISmartWeight=0.0;
   lastAIAverageAccuracy=0.50;
   lastMicroProbability=0.50;
   lastMicroDisagreement=0.0;
   lastMicroBuyVotes=0;
   lastMicroSellVotes=0;
   lastMicroNeutralVotes=0;
   lastAIDeepReliability=0.50;
   lastAIMicroReliability=0.50;
   lastAIFusionQuality=0.50;
   lastAISoftTarget=0.50;
   lastAIRegimeStability=0.50;
   lastAIMetaProbability=0.50;
   lastAICrossTimeframeScore=0.0;
   lastAIAdaptiveRate=1.0;
   lastAIHierarchicalPrior=0.50;
   lastAIDriftScore=0.0;
   lastAISpecialistConsensus=0.50;
   lastAIEntropyConfidence=0.50;
}

double AIModelFeature(int model,int featureIndex,double value)
{
   double scale=1.0;

   // Model 0: trend/momentum uzmani.
   if(model==0)
   {
      if((featureIndex>=2 && featureIndex<=6) ||
         featureIndex==16 || featureIndex==17 ||
         featureIndex==18 || featureIndex==19 ||
         featureIndex==21 || featureIndex==22)
         scale=1.35;
      if(featureIndex==13 || featureIndex==10 || featureIndex==11)
         scale=0.80;
   }
   // Model 1: donus/ortalama uzmani.
   else if(model==1)
   {
      if(featureIndex==8 || featureIndex==9 ||
         featureIndex==10 || featureIndex==11 || featureIndex==12 ||
         featureIndex==13 || featureIndex==15)
         scale=1.40;
      if(featureIndex>=2 && featureIndex<=6)
         scale=0.80;
   }
   // Model 2: kirilim/volatilite uzmani.
   else if(model==2)
   {
      if(featureIndex==7 || featureIndex==14 ||
         featureIndex==17 || featureIndex==20 || featureIndex==23)
         scale=1.45;
      if(featureIndex==13)
         scale=1.20;
   }
   // Model 3: RSI/Bollinger ve donus gucu uzmani.
   else if(model==3)
   {
      if(featureIndex==13 || featureIndex==15 ||
         featureIndex==24 || featureIndex==25)
         scale=1.55;
      if(featureIndex==8 || featureIndex==9)
         scale=1.25;
   }
   // Model 4: spread, tick ve yurutme kalitesi uzmani.
   else
   {
      if(featureIndex==23 || featureIndex==26 || featureIndex==27)
         scale=1.65;
      if(featureIndex==0 || featureIndex==1 || featureIndex==14)
         scale=1.20;
   }

   return ClampValue(value*scale,-1.5,1.5);
}

double AIForward(int model,double &inputs[],double &hidden1[],double &hidden2[])
{
   ArrayResize(hidden1,AI_HIDDEN_1);
   ArrayResize(hidden2,AI_HIDDEN_2);

   for(int i=0;i<AI_HIDDEN_1;i++)
   {
      double sum=aiB1[model][i];
      for(int j=0;j<AI_INPUTS;j++)
         sum+=aiW1[model][i][j]*AIModelFeature(model,j,inputs[j]);
      hidden1[i]=MathTanh(sum);
   }

   for(int k=0;k<AI_HIDDEN_2;k++)
   {
      double sum=aiB2[model][k];
      for(int i=0;i<AI_HIDDEN_1;i++)
         sum+=aiW2[model][k][i]*hidden1[i];
      hidden2[k]=MathTanh(sum);
   }

   double output=aiB3[model];
   for(int k=0;k<AI_HIDDEN_2;k++)
      output+=aiW3[model][k]*hidden2[k];

   return AISigmoid(output);
}

double AIRegimeWeight(int model,double &inputs[])
{
   if(!AI_Rejim_Agirliklama)
      return 1.0;

   if(model==0)
      return 0.50+MathAbs(inputs[6])+MathAbs(inputs[16])+
             0.50*MathAbs(inputs[22]);

   if(model==1)
      return 0.50+MathAbs(inputs[13])+MathAbs(inputs[10])+
             0.50*MathAbs(inputs[15]);

   if(model==2)
      return 0.50+MathAbs(inputs[20])+MathAbs(inputs[7])+
             0.50*MathAbs(inputs[14]);

   if(model==3)
      return 0.50+MathAbs(inputs[24])+MathAbs(inputs[25])+
             0.50*MathAbs(inputs[13]);

   return 0.50+MathAbs(inputs[26])+MathAbs(inputs[27])+
          0.50*MathAbs(inputs[23]);
}

double AIAdaptiveLearningMultiplier(double &inputs[])
{
   if(!AI_Adaptif_Ogrenme)
      return 1.0;

   double trendStrength=ClampValue((MathAbs(inputs[3])+MathAbs(inputs[6])+
                                   MathAbs(inputs[16])+MathAbs(inputs[17]))/4.0,
                                   0.0,1.0);
   double structure=ClampValue((MathAbs(inputs[10])+MathAbs(inputs[11])+
                                MathAbs(inputs[18])+MathAbs(inputs[19]))/4.0,
                                0.0,1.0);
   double noise=ClampValue(0.55*MathAbs(inputs[7])+0.45*MathAbs(inputs[13]),
                           0.0,1.0);
   double execution=ClampValue(0.50+0.50*inputs[26],0.0,1.0);

   double multiplier=0.62+0.42*trendStrength+0.28*structure+
                     0.20*execution-0.30*noise;
   return ClampValue(multiplier,0.45,1.45);
}

double TrainDeepAIModel(int model,double &inputs[],double target)
{
   target=AISmoothTarget(target);
   double hidden1[];
   double hidden2[];
   double probability=AIForward(model,inputs,hidden1,hidden2);
   double predictionError=MathAbs(probability-target);
   double hardExampleWeight=1.0;
   if(AI_Odakli_Zor_Ornek)
      hardExampleWeight=0.70+1.90*predictionError*predictionError;

   double sampleWeight=ClampValue(AIRegimeWeight(model,inputs)*
                                  hardExampleWeight,0.30,4.0);
   double outputGradient=AIClipGradient((probability-target)*sampleWeight);
   double gradient2[24];
   double gradient1[48];

   for(int k=0;k<AI_HIDDEN_2;k++)
      gradient2[k]=AIClipGradient(outputGradient*aiW3[model][k]*
                                 (1.0-hidden2[k]*hidden2[k]));

   for(int i=0;i<AI_HIDDEN_1;i++)
   {
      double propagated=0.0;
      for(int k=0;k<AI_HIDDEN_2;k++)
         propagated+=gradient2[k]*aiW2[model][k][i];
      gradient1[i]=AIClipGradient(propagated*(1.0-hidden1[i]*hidden1[i]));
   }

   // Deneyim arttıkça öğrenme hızını yumuşakça azalt; zor örnekte biraz artır.
   double experienceDecay=0.65+0.35/MathSqrt(1.0+(double)aiTrainingCount/5000.0);
   double adaptiveRate=AIAdaptiveLearningMultiplier(inputs);
   lastAIAdaptiveRate=adaptiveRate;
   double learningRate=ClampValue(AI_Ogrenme_Hizi,0.000001,0.05)*
                       (0.90+0.08*model)*
                       (0.80+0.45*predictionError)*experienceDecay*adaptiveRate;
   double decay=ClampValue(AI_Agirlik_Curumesi,0.0,0.01);

   for(int k=0;k<AI_HIDDEN_2;k++)
      aiW3[model][k]-=learningRate*(outputGradient*hidden2[k]+
                                    decay*aiW3[model][k]);
   aiB3[model]-=learningRate*outputGradient;

   for(int k=0;k<AI_HIDDEN_2;k++)
   {
      for(int i=0;i<AI_HIDDEN_1;i++)
         aiW2[model][k][i]-=learningRate*(gradient2[k]*hidden1[i]+
                                         decay*aiW2[model][k][i]);
      aiB2[model][k]-=learningRate*gradient2[k];
   }

   for(int i=0;i<AI_HIDDEN_1;i++)
   {
      for(int j=0;j<AI_INPUTS;j++)
      {
         double modelInput=AIModelFeature(model,j,inputs[j]);
         aiW1[model][i][j]-=learningRate*(gradient1[i]*modelInput+
                                         decay*aiW1[model][i][j]);
      }
      aiB1[model][i]-=learningRate*gradient1[i];
   }

   // Sadece doğru/yanlış yerine olasılık kalitesini de öğrenme başarısına kat.
   double probabilisticQuality=1.0-MathAbs(probability-target);
   aiModelAccuracy[model]=0.985*aiModelAccuracy[model]+
                          0.015*ClampValue(probabilisticQuality,0.0,1.0);
   if(AI_Cift_Hiz_Basari)
      aiModelFastQuality[model]=0.94*aiModelFastQuality[model]+
                                0.06*ClampValue(probabilisticQuality,0.0,1.0);

   double safeProbability=ClampValue(probability,0.000001,0.999999);
   return -(target*MathLog(safeProbability)+
            (1.0-target)*MathLog(1.0-safeProbability));
}

void TrainDeepAI(double &inputs[],double target)
{
   double totalLoss=0.0;
   for(int model=0;model<AI_MODELS;model++)
      totalLoss+=TrainDeepAIModel(model,inputs,target);

   double deepLoss=totalLoss/AI_MODELS;
   double deepProbability=AIEnsembleProbability(inputs);
   double microLoss=TrainMicroNetworks(inputs,target,deepProbability);
   double microWeight=ClampValue(AI_Mikro_Agirlik,0.0,1.0);
   lastAILoss=(1.0-microWeight)*deepLoss+microWeight*microLoss;
   aiTrainingCount++;

   int saveInterval=MathMax(1,AI_Ag_Kayit_Araligi);
   if(aiTrainingCount%saveInterval==0)
      SaveNeuralState(false);
}

double AIEnsembleProbability(double &inputs[])
{
   double weightTotal=0.0;
   double probabilityTotal=0.0;

   for(int model=0;model<AI_MODELS;model++)
   {
      double hidden1[];
      double hidden2[];
      double probability=AIForward(model,inputs,hidden1,hidden2);
      lastAIModelProbability[model]=probability;

      double accuracyWeight=1.0;
      if(AI_Basari_Agirliklama)
         accuracyWeight=0.15+
            0.55*MathPow(ClampValue(aiModelAccuracy[model],0.10,0.95),2.0)+
            0.70*MathPow(ClampValue(aiModelFastQuality[model],0.10,0.95),3.0);

      double regimeWeight=ClampValue(AIRegimeWeight(model,inputs),0.25,3.0);
      double weight=accuracyWeight*regimeWeight;
      probabilityTotal+=probability*weight;
      weightTotal+=weight;
   }

   double ensemble=weightTotal>0.0?probabilityTotal/weightTotal:0.50;
   double variance=0.0;
   for(int model=0;model<AI_MODELS;model++)
   {
      double delta=lastAIModelProbability[model]-ensemble;
      variance+=delta*delta;
   }
   lastAIDisagreement=MathSqrt(variance/AI_MODELS);

   return ClampValue(ensemble,0.000001,0.999999);
}

int ActiveMicroNetworkCount()
{
   return MathMax(AI_MICRO_MINIMUM,
                  MathMin(AI_MICRO_CAPACITY,AI_Ag_Sayisi));
}

void BuildMicroLatent(double &inputs[],double deepProbability,
                      double &latent[])
{
   ArrayResize(latent,AI_MICRO_INPUTS);
   latent[0]=inputs[3];
   latent[1]=inputs[6];
   latent[2]=inputs[25];
   latent[3]=inputs[20];
   latent[4]=inputs[24];
   latent[5]=inputs[26];
   latent[6]=inputs[27];
   latent[7]=2.0*deepProbability-1.0;
}

double AIMicroFeature(int network,int featureIndex,double value)
{
   int style=network%8;
   double v=ClampValue(value,-1.75,1.75);
   double scale=1.0;

   if(style==0 && (featureIndex==0 || featureIndex==1 || featureIndex==7))
      scale=1.50; // trend/momentum
   else if(style==1 && (featureIndex==2 || featureIndex==4))
      scale=1.55; // mean-reversion / z-score
   else if(style==2 && (featureIndex==3 || featureIndex==5))
      scale=1.60; // breakout + execution
   else if(style==3 && (featureIndex==5 || featureIndex==6))
      scale=1.45; // spread/tick
   else if(style==4)
   {
      // Büyük sinyalleri kuvvetlendir, küçüğü bastır.
      double signedSquare=v>=0.0?v*v:-v*v;
      return ClampValue(signedSquare,-1.75,1.75);
   }
   else if(style==5)
   {
      // Küçük ama tutarlı sinyallere duyarlı uzman.
      double root=MathSqrt(MathAbs(v));
      return ClampValue(v>=0.0?root:-root,-1.75,1.75);
   }
   else if(style==6)
      return MathTanh(1.80*v);
   else if(style==7)
      scale=0.85+0.10*(featureIndex%4);

   return ClampValue(v*scale,-1.75,1.75);
}

double AIMicroForward(int network,double &latent[])
{
   double sum=aiMicroB[network];
   for(int j=0;j<AI_MICRO_INPUTS;j++)
      sum+=aiMicroW[network][j]*AIMicroFeature(network,j,latent[j]);
   return AISigmoid(sum);
}

double AIMicroRegimeWeight(int network,double &latent[])
{
   if(!AI_Rejim_Agirliklama)
      return 1.0;

   int style=network%5;
   if(style==0) return 0.50+MathAbs(latent[0])+MathAbs(latent[1]);
   if(style==1) return 0.50+MathAbs(latent[2])+MathAbs(latent[4]);
   if(style==2) return 0.50+MathAbs(latent[3])+MathAbs(latent[5]);
   if(style==3) return 0.50+MathAbs(latent[5])+MathAbs(latent[6]);
   return 0.75+MathAbs(latent[7]);
}

double AIMicroEnsembleProbability(double &inputs[],double deepProbability)
{
   double latent[];
   BuildMicroLatent(inputs,deepProbability,latent);

   int active=ActiveMicroNetworkCount();
   double weightedProbability=0.0;
   double weightedSquare=0.0;
   double weightTotal=0.0;
   int buyVotes=0;
   int sellVotes=0;
   int neutralVotes=0;

   for(int network=0;network<active;network++)
   {
      double probability=AIMicroForward(network,latent);
      double accuracyWeight=1.0;
      if(AI_Basari_Agirliklama)
         accuracyWeight=0.12+
            0.48*MathPow(ClampValue(aiMicroAccuracy[network],0.10,0.95),2.0)+
            0.72*MathPow(ClampValue(aiMicroFastQuality[network],0.10,0.95),3.0);

      double regimeWeight=ClampValue(AIMicroRegimeWeight(network,latent),
                                     0.25,3.0);
      double weight=accuracyWeight*regimeWeight;
      weightedProbability+=probability*weight;
      weightedSquare+=probability*probability*weight;
      weightTotal+=weight;

      if(probability>0.505) buyVotes++;
      else if(probability<0.495) sellVotes++;
      else neutralVotes++;
   }

   double ensemble=weightTotal>0.0?weightedProbability/weightTotal:0.50;
   double secondMoment=weightTotal>0.0?weightedSquare/weightTotal:0.25;
   lastMicroDisagreement=MathSqrt(MathMax(0.0,
                                         secondMoment-ensemble*ensemble));
   lastMicroProbability=ClampValue(ensemble,0.000001,0.999999);
   lastMicroBuyVotes=buyVotes;
   lastMicroSellVotes=sellVotes;
   lastMicroNeutralVotes=neutralVotes;
   return lastMicroProbability;
}

double TrainMicroNetworks(double &inputs[],double target,
                          double deepProbability)
{
   target=AISmoothTarget(target);
   double latent[];
   BuildMicroLatent(inputs,deepProbability,latent);

   int active=ActiveMicroNetworkCount();
   double experienceDecay=0.70+0.30/MathSqrt(1.0+(double)aiTrainingCount/8000.0);
   double learningRate=ClampValue(AI_Ogrenme_Hizi*0.18,0.0000001,0.01)*
                       experienceDecay*AIAdaptiveLearningMultiplier(inputs);
   double decay=ClampValue(AI_Agirlik_Curumesi,0.0,0.01);
   double totalLoss=0.0;

   for(int network=0;network<active;network++)
   {
      double probability=AIMicroForward(network,latent);
      double predictionError=MathAbs(probability-target);
      double hardExampleWeight=1.0;
      if(AI_Odakli_Zor_Ornek)
         hardExampleWeight=0.75+1.55*predictionError*predictionError;
      double sampleWeight=ClampValue(AIMicroRegimeWeight(network,latent)*
                                     hardExampleWeight,0.30,3.5);
      double gradient=AIClipGradient((probability-target)*sampleWeight);
      double networkRate=learningRate*(0.82+0.04*(network%9))*
                         (0.82+0.35*predictionError);

      for(int j=0;j<AI_MICRO_INPUTS;j++)
      {
         double modelInput=AIMicroFeature(network,j,latent[j]);
         aiMicroW[network][j]-=networkRate*(gradient*modelInput+
                                           decay*aiMicroW[network][j]);
      }
      aiMicroB[network]-=networkRate*gradient;

      double probabilisticQuality=1.0-MathAbs(probability-target);
      aiMicroAccuracy[network]=0.995*aiMicroAccuracy[network]+
                               0.005*ClampValue(probabilisticQuality,0.0,1.0);
      if(AI_Cift_Hiz_Basari)
         aiMicroFastQuality[network]=0.97*aiMicroFastQuality[network]+
                                     0.03*ClampValue(probabilisticQuality,0.0,1.0);

      double safeProbability=ClampValue(probability,0.000001,0.999999);
      totalLoss+=-(target*MathLog(safeProbability)+
                   (1.0-target)*MathLog(1.0-safeProbability));
   }

   return active>0?totalLoss/active:0.0;
}

double AIDeepExpertConsensus()
{
   int buyVotes=0;
   int sellVotes=0;
   double accuracyTotal=0.0;

   for(int model=0;model<AI_MODELS;model++)
   {
      if(lastAIModelProbability[model]>=0.50) buyVotes++;
      else sellVotes++;
      accuracyTotal+=ClampValue(aiModelAccuracy[model],0.0,1.0);
   }

   lastAIAverageAccuracy=accuracyTotal/AI_MODELS;
   return (double)MathMax(buyVotes,sellVotes)/AI_MODELS;
}

double AIMicroVoteConsensus()
{
   int directional=lastMicroBuyVotes+lastMicroSellVotes;
   if(directional<=0)
      return 0.50;

   return (double)MathMax(lastMicroBuyVotes,lastMicroSellVotes)/directional;
}

double AISmartDecisionWeight()
{
   double confidenceEdge=ClampValue((lastAIConfidence-0.50)*2.0,0.0,1.0);
   double accuracyQuality=ClampValue((lastAIAverageAccuracy-0.45)/0.30,
                                     0.0,1.0);
   double disagreement=ClampValue(
      0.55*lastMicroDisagreement+0.45*lastAIDisagreement,
      0.0,0.50);
   double experience=ClampValue((double)aiTrainingCount/6000.0,0.10,1.0);
   double memoryQuality=ClampValue(lastMemoryConfidence,0.0,1.0);
   double fusionQuality=ClampValue(lastAIFusionQuality,0.0,1.0);

   double multiplier=0.35+0.55*confidenceEdge+
                     0.35*lastAIConsensus+
                     0.25*accuracyQuality+
                     0.20*experience+
                     0.20*memoryQuality+
                     0.25*fusionQuality+
                     0.20*lastAIRegimeStability-
                     1.35*disagreement;

   return ClampValue(AI_Agirlik*multiplier,
                     AI_Dinamik_Min_Agirlik,
                     AI_Dinamik_Max_Agirlik);
}

double AINormalizedMomentum(MqlRates &bars[],int offset,int length,
                            double averageRange)
{
   int last=offset+length;
   if(last>=ArraySize(bars))
      return 0.0;
   return SafeDivide(bars[offset].close-bars[last].close,
                     MathMax(EnginePoint(),averageRange)*MathSqrt((double)length));
}

double AIChannelPosition(MqlRates &bars[],int offset,int length)
{
   int last=MathMin(ArraySize(bars)-1,offset+length);
   double highest=bars[offset].high;
   double lowest=bars[offset].low;

   for(int i=offset;i<=last;i++)
   {
      if(bars[i].high>highest) highest=bars[i].high;
      if(bars[i].low<lowest) lowest=bars[i].low;
   }

   return 2.0*SafeDivide(bars[offset].close-lowest,
                         MathMax(EnginePoint(),highest-lowest))-1.0;
}

double AIPersistence(MqlRates &bars[],int offset,int length)
{
   int last=MathMin(ArraySize(bars),offset+length);
   double score=0.0;
   int count=0;

   for(int i=offset;i<last;i++)
   {
      if(bars[i].close>bars[i].open) score+=1.0;
      else if(bars[i].close<bars[i].open) score-=1.0;
      count++;
   }

   return count>0?score/count:0.0;
}

double AIHistoricalMultiHorizonFeature(MqlRates &bars[],int offset,
                                       int requestedHorizons,double averageRange)
{
   int size=ArraySize(bars);
   int maximum=MathMin(requestedHorizons,size-offset-1);
   if(maximum<1) return 0.0;

   double weighted=0.0;
   double weightTotal=0.0;
   double absTotal=0.0;
   int positive=0;
   int negative=0;

   for(int horizon=1;horizon<=maximum;horizon++)
   {
      double move=bars[offset].close-bars[offset+horizon].close;
      double scale=MathMax(EnginePoint(),averageRange*MathSqrt((double)horizon));
      double normalized=MathTanh(move/scale);
      double weight=1.0/MathSqrt((double)horizon);

      if(horizon>=12)  weight*=1.04;
      if(horizon>=24)  weight*=1.07;
      if(horizon>=48)  weight*=1.10;
      if(horizon>=72)  weight*=1.12;
      if(horizon>=96)  weight*=1.14;
      if(horizon>=120) weight*=1.16;
      if(horizon>=160) weight*=1.18;
      if(horizon>=192) weight*=1.20;
      if(horizon>=224) weight*=1.22;
      if(AI_Zamansal_Dikkat)
         weight*=0.72+0.28*MathAbs(normalized);

      weighted+=weight*normalized;
      absTotal+=weight*MathAbs(normalized);
      weightTotal+=weight;
      if(move>0.0) positive++;
      else if(move<0.0) negative++;
   }

   if(weightTotal<=0.0) return 0.0;
   int directional=positive+negative;
   double agreement=directional>0?
                    (double)MathMax(positive,negative)/directional:0.50;
   double strength=absTotal/weightTotal;
   double quality=ClampValue(0.40+0.40*agreement+0.20*strength,0.30,1.0);
   return ClampValue((weighted/weightTotal)*quality,-1.0,1.0);
}

bool BuildAIInputVector(MqlRates &bars[],int offset,
                        double mtfM15,double mtfH1,double directScore,
                        double &features[])
{
   if(ArraySize(bars)<offset+AI_MULTI_HORIZONS+2)
      return false;

   ArrayResize(features,AI_INPUTS);

   double averageRange=0.0;
   double averageVolume=0.0;
   double meanClose=0.0;
   for(int i=offset;i<offset+20;i++)
   {
      averageRange+=MathMax(EnginePoint(),bars[i].high-bars[i].low);
      averageVolume+=(double)bars[i].tick_volume;
      meanClose+=bars[i].close;
   }
   averageRange=MathMax(EnginePoint(),averageRange/20.0);
   averageVolume=MathMax(1.0,averageVolume/20.0);
   meanClose/=20.0;

   double variance=0.0;
   for(int i=offset;i<offset+20;i++)
   {
      double delta=bars[i].close-meanClose;
      variance+=delta*delta;
   }
   variance/=20.0;

   double currentRange=MathMax(EnginePoint(),bars[offset].high-bars[offset].low);
   double upperWick=bars[offset].high-
                    MathMax(bars[offset].open,bars[offset].close);
   double lowerWick=MathMin(bars[offset].open,bars[offset].close)-
                    bars[offset].low;

   double gains=0.0;
   double losses=0.0;
   for(int i=offset;i<offset+14;i++)
   {
      double change=bars[i].close-bars[i+1].close;
      if(change>0.0) gains+=change;
      else losses-=change;
   }

   double recentMean5=0.0;
   double mean20=0.0;
   for(int i=offset;i<offset+20;i++)
   {
      mean20+=bars[i].close;
      if(i<offset+5) recentMean5+=bars[i].close;
   }
   recentMean5/=5.0;
   mean20/=20.0;

   double recentMean6=0.0;
   double olderMean6=0.0;
   for(int i=0;i<6;i++)
   {
      recentMean6+=bars[offset+i].close;
      olderMean6+=bars[offset+6+i].close;
   }
   recentMean6/=6.0;
   olderMean6/=6.0;

   double priorHigh=bars[offset+1].high;
   double priorLow=bars[offset+1].low;
   for(int i=offset+2;i<=offset+20;i++)
   {
      if(bars[i].high>priorHigh) priorHigh=bars[i].high;
      if(bars[i].low<priorLow) priorLow=bars[i].low;
   }
   double breakout=0.0;
   if(bars[offset].close>priorHigh)
      breakout=1.0+SafeDivide(bars[offset].close-priorHigh,averageRange);
   else if(bars[offset].close<priorLow)
      breakout=-1.0-SafeDivide(priorLow-bars[offset].close,averageRange);

   features[0]=SafeDivide(bars[offset].close-bars[offset].open,currentRange);
   features[1]=SafeDivide(bars[offset].close-bars[offset+1].close,averageRange);
   features[2]=AINormalizedMomentum(bars,offset,3,averageRange);
   features[3]=AINormalizedMomentum(bars,offset,5,averageRange);
   features[4]=AINormalizedMomentum(bars,offset,8,averageRange);
   features[5]=AINormalizedMomentum(bars,offset,13,averageRange);
   features[6]=AINormalizedMomentum(bars,offset,21,averageRange);
   features[7]=SafeDivide(currentRange,averageRange)-1.0;
   features[8]=-SafeDivide(upperWick,currentRange);
   features[9]=SafeDivide(lowerWick,currentRange);
   features[10]=AIChannelPosition(bars,offset,5);
   features[11]=AIChannelPosition(bars,offset,13);
   features[12]=AIChannelPosition(bars,offset,21);
   features[13]=SafeDivide(bars[offset].close-meanClose,
                           MathMax(EnginePoint(),MathSqrt(variance)));
   features[14]=SafeDivide((double)bars[offset].tick_volume,averageVolume)-1.0;
   features[15]=SafeDivide(gains-losses,MathMax(EnginePoint(),gains+losses));
   features[16]=SafeDivide(recentMean5-mean20,averageRange);
   features[17]=AIHistoricalMultiHorizonFeature(bars,offset,AI_MULTI_HORIZONS,averageRange);
   features[18]=AIPersistence(bars,offset,5);
   features[19]=AIPersistence(bars,offset,10);
   features[20]=breakout;
   features[21]=mtfM15;
   features[22]=mtfH1;
   features[23]=directScore;
   // RSI momentumu: -1 asiri satis yonu, +1 asiri alim yonu.
   features[24]=features[15];
   // Bollinger benzeri standart sapma konumu.
   features[25]=SafeDivide(bars[offset].close-meanClose,
                           MathMax(EnginePoint(),2.0*MathSqrt(variance)));
   features[26]=0.0;
   features[27]=0.0;

   // Canli ornekte yurutme kalitesi ve tick dengesi de kullanilir.
   if(offset==0)
   {
      double spreadQuality=0.50;
      if(lastCurrentSpread>=0 && lastMinimumSpread>=0)
         spreadQuality=ClampValue((double)(lastMinimumSpread+1)/
                                  (lastCurrentSpread+1),0.0,1.0);
      features[26]=2.0*spreadQuality-1.0;
      features[27]=ClampValue(lastTickImbalance,-1.0,1.0);
   }

   for(int i=0;i<AI_INPUTS;i++)
   {
      if(!MathIsValidNumber(features[i])) features[i]=0.0;
      features[i]=MathTanh(ClampValue(features[i],-5.0,5.0));
   }

   return true;
}

string AIHistoryMemoryFileName()
{
   // V68: Ortak Forex hafizasi. Parite degisince 10K modeli sifirlama/yukleme yok.
   return "V75_M15_GLOBAL_FOREX_HIER_AI_MEMORY_"+IntegerToString((int)InpTF)+".bin";
}

string AINeuralStateFileName()
{
   return "V75_M15_GLOBAL_FOREX_HIER_AI_STATE_"+IntegerToString((int)InpTF)+".bin";
}

bool SaveNeuralState(bool forceSave=false)
{
   if(!AI_Ag_Kalici_Ogrenme)
      return false;

   ulong nowMs=GetTickCount64();
   if(!forceSave && nowMs-aiLastStateSaveMs<(ulong)MathMax(1000,AI_Gecmis_Kayit_Araligi_MS))
      return false;

   int handle=FileOpen(AINeuralStateFileName(),
                       FILE_BIN|FILE_WRITE|FILE_COMMON);
   if(handle==INVALID_HANDLE)
   {
      Print("Deep AI state save failed: ",GetLastError());
      return false;
   }

   int active=ActiveMicroNetworkCount();
   FileWriteInteger(handle,6402,INT_VALUE);
   FileWriteInteger(handle,(int)InpTF,INT_VALUE);
   FileWriteInteger(handle,AI_INPUTS,INT_VALUE);
   FileWriteInteger(handle,AI_HIDDEN_1,INT_VALUE);
   FileWriteInteger(handle,AI_HIDDEN_2,INT_VALUE);
   FileWriteInteger(handle,AI_MODELS,INT_VALUE);
   FileWriteInteger(handle,active,INT_VALUE);
   FileWriteInteger(handle,aiTrainingCount,INT_VALUE);

   for(int model=0;model<AI_MODELS;model++)
   {
      for(int i=0;i<AI_HIDDEN_1;i++)
         for(int j=0;j<AI_INPUTS;j++)
            FileWriteDouble(handle,aiW1[model][i][j]);
      for(int i=0;i<AI_HIDDEN_1;i++)
         FileWriteDouble(handle,aiB1[model][i]);

      for(int k=0;k<AI_HIDDEN_2;k++)
         for(int i=0;i<AI_HIDDEN_1;i++)
            FileWriteDouble(handle,aiW2[model][k][i]);
      for(int k=0;k<AI_HIDDEN_2;k++)
         FileWriteDouble(handle,aiB2[model][k]);
      for(int k=0;k<AI_HIDDEN_2;k++)
         FileWriteDouble(handle,aiW3[model][k]);

      FileWriteDouble(handle,aiB3[model]);
      FileWriteDouble(handle,aiModelAccuracy[model]);
   }

   for(int network=0;network<active;network++)
   {
      for(int j=0;j<AI_MICRO_INPUTS;j++)
         FileWriteDouble(handle,aiMicroW[network][j]);
      FileWriteDouble(handle,aiMicroB[network]);
      FileWriteDouble(handle,aiMicroAccuracy[network]);
   }

   FileClose(handle);
   aiLastStateSaveMs=nowMs;
   aiStateLoaded=true;
   return true;
}

bool LoadNeuralState()
{
   aiStateLoaded=false;
   if(!AI_Ag_Kalici_Ogrenme)
      return false;

   int handle=FileOpen(AINeuralStateFileName(),
                       FILE_BIN|FILE_READ|FILE_COMMON);
   if(handle==INVALID_HANDLE)
      return false;

   int signature=FileReadInteger(handle,INT_VALUE);
   int timeframe=FileReadInteger(handle,INT_VALUE);
   int inputs=FileReadInteger(handle,INT_VALUE);
   int hidden1=FileReadInteger(handle,INT_VALUE);
   int hidden2=FileReadInteger(handle,INT_VALUE);
   int models=FileReadInteger(handle,INT_VALUE);
   int active=FileReadInteger(handle,INT_VALUE);
   int storedTrainingCount=FileReadInteger(handle,INT_VALUE);

   int expectedActive=ActiveMicroNetworkCount();
   long deepDoubles=(long)AI_MODELS*AI_HIDDEN_1*AI_INPUTS+
                    (long)AI_MODELS*AI_HIDDEN_1+
                    (long)AI_MODELS*AI_HIDDEN_2*AI_HIDDEN_1+
                    (long)AI_MODELS*AI_HIDDEN_2+
                    (long)AI_MODELS*AI_HIDDEN_2+
                    (long)AI_MODELS*2;
   long microDoubles=(long)expectedActive*(AI_MICRO_INPUTS+2);
   long expectedBytes=32+(deepDoubles+microDoubles)*8;

   if(signature!=6402 || timeframe!=(int)InpTF ||
      inputs!=AI_INPUTS || hidden1!=AI_HIDDEN_1 ||
      hidden2!=AI_HIDDEN_2 || models!=AI_MODELS ||
      active!=expectedActive || (long)FileSize(handle)<expectedBytes)
   {
      FileClose(handle);
      return false;
   }

   for(int model=0;model<AI_MODELS;model++)
   {
      for(int i=0;i<AI_HIDDEN_1;i++)
         for(int j=0;j<AI_INPUTS;j++)
            aiW1[model][i][j]=FileReadDouble(handle);
      for(int i=0;i<AI_HIDDEN_1;i++)
         aiB1[model][i]=FileReadDouble(handle);

      for(int k=0;k<AI_HIDDEN_2;k++)
         for(int i=0;i<AI_HIDDEN_1;i++)
            aiW2[model][k][i]=FileReadDouble(handle);
      for(int k=0;k<AI_HIDDEN_2;k++)
         aiB2[model][k]=FileReadDouble(handle);
      for(int k=0;k<AI_HIDDEN_2;k++)
         aiW3[model][k]=FileReadDouble(handle);

      aiB3[model]=FileReadDouble(handle);
      aiModelAccuracy[model]=FileReadDouble(handle);
      aiModelFastQuality[model]=aiModelAccuracy[model];
   }

   for(int network=0;network<expectedActive;network++)
   {
      for(int j=0;j<AI_MICRO_INPUTS;j++)
         aiMicroW[network][j]=FileReadDouble(handle);
      aiMicroB[network]=FileReadDouble(handle);
      aiMicroAccuracy[network]=FileReadDouble(handle);
      aiMicroFastQuality[network]=aiMicroAccuracy[network];
   }

   FileClose(handle);
   aiTrainingCount=MathMax(0,storedTrainingCount);
   aiLastStateSaveMs=GetTickCount64();
   aiStateLoaded=true;
   return true;
}

int AIHistoryHash(double &features[],int seed)
{
   long hash=104729+seed*8191;
   int usable=ArraySize(features)>=26?23:MathMin(21,ArraySize(features));

   for(int i=0;i<usable;i++)
   {
      int featureIndex=i<21?i:i+3;
      int quantized=(int)MathRound((ClampValue(features[featureIndex],-1.0,1.0)+1.0)*127.5);
      hash=(hash*131+quantized*(i+17)+seed*29)%2147483629;
   }

   if(hash<0) hash=-hash;
   return (int)(hash%AI_MEMORY_BUCKETS);
}

void ClearHistoryMemory()
{
   for(int i=0;i<AI_MEMORY_BUCKETS;i++)
   {
      aiMemoryCount[i]=0.0;
      aiMemoryUpSum[i]=0.0;
   }

   aiHistoryProcessed=0;
   aiHistoryNextShift=2;
   aiHistoryOldestTime=0;
   aiHistoryComplete=false;
   aiHistoryBatchCount=0;
   aiHistoryEpoch=0;
   aiHistoryUniqueAvailable=0;
   aiHistoryDeepSamples=0;
   aiHistoryThroughput=0.0;
   aiHistoryRateWindowStartMs=GetTickCount64();
   aiHistoryRateWindowSamples=0;
   aiHistoryLastPassMs=GetTickCount64();
   lastMemoryProbability=0.50;
   lastMemoryConfidence=0.0;
   lastMemoryBucket=-1;
}

void RecordHistoryPattern(double &features[],double target)
{
   int seeds[8]={17,43,97,151,223,307,419,557};

   // Tum gorulen tarih ornekleri kalici istatistik hafizasina eklenir.
   // Sayaclarda unutma/decay uygulanmaz; tekrar epochlar yeni deneyim olarak birikir.
   for(int i=0;i<8;i++)
   {
      int bucket=AIHistoryHash(features,seeds[i]);
      aiMemoryCount[bucket]+=1.0;
      aiMemoryUpSum[bucket]+=target;
   }
}

double HistoryMemoryProbability(double &features[])
{
   int seeds[8]={17,43,97,151,223,307,419,557};
   double count=0.0;
   double upSum=0.0;

   for(int i=0;i<8;i++)
   {
      int bucket=AIHistoryHash(features,seeds[i]);
      if(i==0) lastMemoryBucket=bucket;
      count+=aiMemoryCount[bucket];
      upSum+=aiMemoryUpSum[bucket];
   }

   double minimumSamples=MathMax(1,AI_Hafiza_Min_Ornek)*8.0;
   if(count<minimumSamples)
   {
      lastMemoryProbability=0.50;
      lastMemoryConfidence=0.0;
      return lastMemoryProbability;
   }

   lastMemoryProbability=ClampValue(SafeDivide(upSum,count),0.01,0.99);
   double directionConfidence=MathAbs(lastMemoryProbability-0.50)*2.0;
   double sampleConfidence=count/(count+minimumSamples*5.0);
   lastMemoryConfidence=ClampValue(directionConfidence*sampleConfidence,0.0,1.0);
   return lastMemoryProbability;
}

bool SaveHistoryMemory(bool forceSave=false)
{
   if(!AI_Kalici_Hafiza)
      return false;

   ulong nowMs=GetTickCount64();
   if(!forceSave && nowMs-aiLastMemorySaveMs<(ulong)MathMax(1000,AI_Gecmis_Kayit_Araligi_MS))
      return false;

   int handle=FileOpen(AIHistoryMemoryFileName(),
                       FILE_BIN|FILE_WRITE|FILE_COMMON);
   if(handle==INVALID_HANDLE)
   {
      Print("AI memory save open failed: ",GetLastError());
      return false;
   }

   FileWriteInteger(handle,6401,INT_VALUE);
   FileWriteInteger(handle,(int)InpTF,INT_VALUE);
   FileWriteInteger(handle,AI_MEMORY_BUCKETS,INT_VALUE);

   // 60M tekrarli ogrenme ilerlemesi ve kaldigi nokta kalici olarak saklanir.
   FileWriteDouble(handle,(double)aiHistoryProcessed);
   FileWriteDouble(handle,(double)aiHistoryOldestTime);
   FileWriteDouble(handle,(double)aiHistoryNextShift);
   FileWriteDouble(handle,(double)aiHistoryEpoch);
   FileWriteDouble(handle,(double)aiHistoryUniqueAvailable);
   FileWriteDouble(handle,(double)aiHistoryDeepSamples);

   for(int i=0;i<AI_MEMORY_BUCKETS;i++)
   {
      FileWriteDouble(handle,aiMemoryCount[i]);
      FileWriteDouble(handle,aiMemoryUpSum[i]);
   }

   FileClose(handle);
   aiLastMemorySaveMs=nowMs;
   return true;
}

bool LoadHistoryMemory()
{
   if(!AI_Kalici_Hafiza)
      return false;

   int handle=FileOpen(AIHistoryMemoryFileName(),
                       FILE_BIN|FILE_READ|FILE_COMMON);
   if(handle==INVALID_HANDLE)
      return false;

   int signature=FileReadInteger(handle,INT_VALUE);
   int timeframe=FileReadInteger(handle,INT_VALUE);
   int buckets=FileReadInteger(handle,INT_VALUE);

   if(signature!=6401 || timeframe!=(int)InpTF ||
      buckets!=AI_MEMORY_BUCKETS)
   {
      FileClose(handle);
      return false;
   }

   aiHistoryProcessed=(long)FileReadDouble(handle);
   aiHistoryOldestTime=(datetime)FileReadDouble(handle);
   aiHistoryNextShift=(int)FileReadDouble(handle);
   aiHistoryEpoch=(long)FileReadDouble(handle);
   aiHistoryUniqueAvailable=(long)FileReadDouble(handle);
   aiHistoryDeepSamples=(long)FileReadDouble(handle);

   for(int i=0;i<AI_MEMORY_BUCKETS;i++)
   {
      if(FileIsEnding(handle))
      {
         FileClose(handle);
         ClearHistoryMemory();
         return false;
      }

      aiMemoryCount[i]=FileReadDouble(handle);
      aiMemoryUpSum[i]=FileReadDouble(handle);
   }

   FileClose(handle);

   if(aiHistoryNextShift<2)
      aiHistoryNextShift=2;

   aiHistoryRateWindowStartMs=GetTickCount64();
   aiHistoryRateWindowSamples=0;
   aiHistoryLastPassMs=GetTickCount64();
   return true;
}

void RefreshHistoryTarget()
{
   // 60M burada "toplam ogrenme maruziyeti"dir. Brokerda bulunan benzersiz
   // mum sayisi daha azsa ayni tarih epochlar halinde tekrar ogrenilir.
   long available=(long)Bars(EngineSymbol(),InpTF)-AI_MULTI_HORIZONS-10;
   if(available<0) available=0;
   aiHistoryUniqueAvailable=available;

   long requested=AI_Gecmis_Hedef_Mum;
   if(requested<1) requested=1;
   aiHistoryTarget=requested;

   if(aiHistoryProcessed<aiHistoryTarget && available>0)
      aiHistoryComplete=false;
   else if(aiHistoryProcessed>=aiHistoryTarget)
      aiHistoryComplete=true;
}

long MinimumHistoryForTrading()
{
   long requestedMinimum=(long)MathMax(1,AI_Gecmis_Min_Mum);
   if(aiHistoryTarget<=0)
      return requestedMinimum;

   return MathMin(requestedMinimum,aiHistoryTarget);
}

void InitializeHistoryMemory()
{
   ClearHistoryMemory();
   LoadHistoryMemory();
   RefreshHistoryTarget();

   if(aiHistoryProcessed>=aiHistoryTarget && aiHistoryTarget>0)
      aiHistoryComplete=true;
}

void UpdateHistoryThroughput(long processedNow)
{
   ulong now=GetTickCount64();
   if(aiHistoryRateWindowStartMs==0)
      aiHistoryRateWindowStartMs=now;

   aiHistoryRateWindowSamples+=processedNow;
   ulong elapsed=now-aiHistoryRateWindowStartMs;

   if(elapsed>=1000)
   {
      double instant=1000.0*(double)aiHistoryRateWindowSamples/
                     MathMax(1.0,(double)elapsed);
      if(aiHistoryThroughput<=0.0)
         aiHistoryThroughput=instant;
      else
         aiHistoryThroughput=0.70*aiHistoryThroughput+0.30*instant;

      aiHistoryRateWindowSamples=0;
      aiHistoryRateWindowStartMs=now;
   }
}

void StartNextHistoryEpoch()
{
   aiHistoryEpoch++;
   aiHistoryNextShift=2;
   aiHistoryOldestTime=0;
}

void ProcessHistoryMemoryBatch()
{
   RefreshHistoryTarget();

   if(aiHistoryComplete || aiHistoryTarget<=0 || aiHistoryUniqueAvailable<=0)
      return;

   long totalRemaining=aiHistoryTarget-aiHistoryProcessed;
   if(totalRemaining<=0)
   {
      aiHistoryComplete=true;
      SaveHistoryMemory(true);
      SaveNeuralState(true);
      return;
   }

   // Mevcut broker gecmisinin sonuna gelindiyse basa don ve yeni epoch baslat.
   long consumedThisEpoch=(long)MathMax(0,aiHistoryNextShift-2);
   if(consumedThisEpoch>=aiHistoryUniqueAvailable)
   {
      if(AI_Gecmis_Tekrarli_Ogrenme)
         StartNextHistoryEpoch();
      else
      {
         aiHistoryComplete=true;
         SaveHistoryMemory(true);
         SaveNeuralState(true);
         return;
      }
      consumedThisEpoch=0;
   }

   long epochRemaining=aiHistoryUniqueAvailable-consumedThisEpoch;
   if(epochRemaining<=0)
      return;

   // 800K/s bir hedeftir. MQL5 tek thread, CopyRates ve 10K backprop nedeniyle
   // gercek hiz CPU/VPS/broker tarih miktarina baglidir. Batch motoru hedefe
   // yaklasmaya calisir ama terminali kilitlememek icin tek cagriyi sinirlar.
   ulong nowMs=GetTickCount64();
   if(aiHistoryLastPassMs==0) aiHistoryLastPassMs=nowMs;
   ulong elapsedMs=(nowMs>aiHistoryLastPassMs)?(nowMs-aiHistoryLastPassMs):1;
   aiHistoryLastPassMs=nowMs;

   long rateBased=(AI_Gecmis_Hedef_Hiz>0)?
                  (long)MathMax(1000.0,(double)AI_Gecmis_Hedef_Hiz*
                                (double)elapsedMs/1000.0):AI_Gecmis_Parti;

   int requestedBatch=(int)MathMax(250,
                      MathMin(50000.0,
                              MathMax((double)AI_Gecmis_Parti,
                                      (double)rateBased)));
   int batch=(int)MathMin((double)requestedBatch,
                          MathMin((double)totalRemaining,
                                  (double)epochRemaining));
   if(batch<=0)
      return;

   MqlRates bars[];
   ArraySetAsSeries(bars,true);

   int startShift=MathMax(1,aiHistoryNextShift-1);
   int copied=CopyRates(EngineSymbol(),InpTF,startShift,
                        batch+AI_MULTI_HORIZONS+3,bars);

   if(copied<AI_MULTI_HORIZONS+4)
   {
      // Broker bu noktada daha fazla tarih vermiyorsa epochu yeniden baslat.
      if(AI_Gecmis_Tekrarli_Ogrenme)
      {
         StartNextHistoryEpoch();
         SaveHistoryMemory(false);
      }
      return;
   }

   int usable=MathMin(batch,copied-AI_MULTI_HORIZONS-3);
   int recorded=0;
   int deepInterval=MathMax(1,AI_Gecmis_Derin_Egitim_Araligi);

   for(int offset=1;offset<=usable;offset++)
   {
      double features[];
      if(!BuildAIInputVector(bars,offset,0.0,0.0,0.0,features))
         continue;

      double target=AI_Coklu_Ufuk_Ogrenme?
                    AIMultiHorizonTarget(bars,offset):
                    (bars[offset-1].close>bars[offset].close?1.0:0.0);

      // Her tarih ornegi kalici hafizaya girer.
      RecordHistoryPattern(features,target);
      recorded++;

      // 10K ensemble backprop cok daha pahali oldugu icin temsilci araliklarla
      // yapilir. Epochlar tekrarlandikca tum tarih bolgeleri tekrar tekrar egitilir.
      long absoluteSample=aiHistoryProcessed+(long)recorded;
      if(AI_Derin_Ogrenme && (absoluteSample%deepInterval)==0)
      {
         lastAISoftTarget=target;
         TrainDeepAI(features,target);
         aiHistoryDeepSamples++;
      }
   }

   if(recorded<=0)
   {
      if(AI_Gecmis_Tekrarli_Ogrenme)
         StartNextHistoryEpoch();
      return;
   }

   aiHistoryProcessed+=recorded;
   aiHistoryNextShift+=usable;
   aiHistoryOldestTime=bars[usable].time;
   aiHistoryBatchCount++;
   UpdateHistoryThroughput(recorded);

   if(aiHistoryProcessed>=aiHistoryTarget)
      aiHistoryComplete=true;

   // Sik kalici kayit: terminal/VPS kapanirsa ilerleme ve 10K agirliklar kaybolmaz.
   if(aiHistoryBatchCount%5==0 || aiHistoryComplete)
   {
      SaveHistoryMemory(aiHistoryComplete);
      SaveNeuralState(aiHistoryComplete);
   }
}

void WarmupDeepAI()
{
   if(!AI_Derin_Ogrenme)
      return;

   MqlRates bars[];
   ArraySetAsSeries(bars,true);
   int copied=CopyRates(EngineSymbol(),InpTF,1,1200,bars);
   if(copied<AI_MULTI_HORIZONS+120)
      return;

   for(int offset=600;offset>=1;offset--)
   {
      double inputs[];
      if(!BuildAIInputVector(bars,offset,0.0,0.0,0.0,inputs))
         continue;

      double target=AI_Coklu_Ufuk_Ogrenme?
                    AIMultiHorizonTarget(bars,offset):
                    (bars[offset-1].close>bars[offset].close?1.0:0.0);
      lastAISoftTarget=target;
      TrainDeepAI(inputs,target);
   }
}

bool UpdateDeepAI(double directScore)
{
   if(!AI_Derin_Ogrenme)
   {
      lastAIProbability=0.50;
      lastAIScore=0.0;
      lastAIConfidence=0.50;
      return false;
   }

   MqlRates bars[];
   ArraySetAsSeries(bars,true);
   int copied=CopyRates(EngineSymbol(),InpTF,1,AI_MULTI_HORIZONS+20,bars);
   if(copied<AI_MULTI_HORIZONS+5)
      return false;

   double mtfM5=(double)ClosedTimeframeDirection(PERIOD_M5);
   double mtfM15=(double)ClosedTimeframeDirection(PERIOD_M15);
   double mtfH1=(double)ClosedTimeframeDirection(PERIOD_H1);
   double mtfH4=(double)ClosedTimeframeDirection(PERIOD_H4);
   double inputs[];
   if(!BuildAIInputVector(bars,0,mtfM15,mtfH1,directScore,inputs))
      return false;

   if(aiLastSampleBar!=bars[0].time)
   {
      if(aiHasPendingSample)
      {
         double pending[];
         ArrayResize(pending,AI_INPUTS);
         for(int i=0;i<AI_INPUTS;i++) pending[i]=aiPendingInput[i];
         double recentRange=MathMax(EnginePoint(),
                              (bars[0].high-bars[0].low+
                               bars[1].high-bars[1].low)*0.50);
         double target=AI_Coklu_Ufuk_Ogrenme?
                       AIOneStepSoftTarget(bars[0].close,bars[1].close,recentRange):
                       (bars[0].close>bars[1].close?1.0:0.0);
         lastAISoftTarget=target;
         TrainDeepAI(pending,target);
         RecordHistoryPattern(pending,target);
      }

      for(int i=0;i<AI_INPUTS;i++) aiPendingInput[i]=inputs[i];
      aiHasPendingSample=true;
      aiLastSampleBar=bars[0].time;
   }

   double deepProbability=AIEnsembleProbability(inputs);
   double microProbability=AIMicroEnsembleProbability(inputs,deepProbability);
   double deepConsensus=AIDeepExpertConsensus();
   double microConsensus=AIMicroVoteConsensus();

   // 384 M15 tabanli ufuk + 12 rejim uzmani + M15/M15/H1/H4 + drift farkindaligi.
   double temporalRegime=0.50;
   lastAITemporalPrior=AITemporalPriorProbability(bars,0,temporalRegime);
   double regimeDirectionScore=0.0;
   lastAIRegimeStability=AIRegimeStabilityFromRates(bars,0,regimeDirectionScore);
   lastAIHierarchicalPrior=AIHierarchicalRegimeProbability(bars,0,lastAISpecialistConsensus);
   lastAIDriftScore=AIMarketDriftScore(bars,0);
   double mtfScore=ClampValue((mtfM5+mtfM15+mtfH1+mtfH4)/4.0,-1.0,1.0);
   lastAICrossTimeframeScore=mtfScore;
   double mtfPrior=AISigmoid(1.75*mtfScore);
   int mtfPositive=0,mtfNegative=0;
   if(mtfM5>0) mtfPositive++; else if(mtfM5<0) mtfNegative++;
   if(mtfM15>0) mtfPositive++; else if(mtfM15<0) mtfNegative++;
   if(mtfH1>0) mtfPositive++; else if(mtfH1<0) mtfNegative++;
   if(mtfH4>0) mtfPositive++; else if(mtfH4<0) mtfNegative++;
   double mtfConsensus=(double)MathMax(mtfPositive,mtfNegative)/4.0;
   lastAIRegimeConsensus=ClampValue(0.30*temporalRegime+
                                     0.22*mtfConsensus+
                                     0.23*lastAIRegimeStability+
                                     0.25*lastAISpecialistConsensus,0.0,1.0);
   if(AI_Rejim_Uzlasma)
      lastAITemporalPrior=ClampValue(0.72*lastAITemporalPrior+0.28*mtfPrior,0.02,0.98);

   // Sabit oran yerine güven/uyuşmazlık/başarıya göre dinamik birleşim.
   double baseMicroWeight=ClampValue(AI_Mikro_Agirlik,0.0,1.0);
   lastAIDeepReliability=ClampValue(0.25+0.45*deepConsensus+
                                   0.30*lastAIAverageAccuracy-
                                   1.50*lastAIDisagreement,0.10,1.0);
   lastAIMicroReliability=ClampValue(0.20+0.55*microConsensus+
                                    0.25*(1.0-lastMicroDisagreement*2.0)-
                                    1.10*lastMicroDisagreement,0.10,1.0);

   double deepWeight=(1.0-baseMicroWeight)*lastAIDeepReliability;
   double microWeight=baseMicroWeight*lastAIMicroReliability;
   if(!AI_Dinamik_Birlestirme)
   {
      deepWeight=1.0-baseMicroWeight;
      microWeight=baseMicroWeight;
   }
   double networkWeightTotal=MathMax(0.000001,deepWeight+microWeight);
   double networkProbability=(deepWeight*deepProbability+
                              microWeight*microProbability)/networkWeightTotal;

   // Rejim tutarliysa zamansal prior daha fazla soz sahibi olur.
   if(AI_Zamansal_Dikkat)
   {
      double temporalWeight=ClampValue(0.08+0.22*lastAIRegimeConsensus,0.08,0.30);
      double hierarchicalWeight=ClampValue(AI_Uzman_Agirlik*
                                           (0.55+0.45*lastAISpecialistConsensus),0.08,0.30);
      double baseWeight=MathMax(0.10,1.0-temporalWeight-hierarchicalWeight);
      double totalWeight=baseWeight+temporalWeight+hierarchicalWeight;
      networkProbability=(baseWeight*networkProbability+
                          temporalWeight*lastAITemporalPrior+
                          hierarchicalWeight*lastAIHierarchicalPrior)/totalWeight;
   }

   double memoryProbability=HistoryMemoryProbability(inputs);
   double memoryWeight=ClampValue(AI_Hafiza_Agirlik,0.0,1.0)*
                       lastMemoryConfidence;
   double baseProbability=(1.0-memoryWeight)*networkProbability+
                          memoryWeight*memoryProbability;

   double directPrior=AISigmoid(1.60*ClampValue(directScore,-1.0,1.0));
   double metaDenominator=0.27+0.18+0.16+0.17+0.22;
   lastAIMetaProbability=ClampValue(
      (0.27*lastAITemporalPrior+
       0.18*mtfPrior+
       0.16*directPrior+
       0.17*memoryProbability+
       0.22*lastAIHierarchicalPrior)/metaDenominator,0.02,0.98);

   double metaWeight=AI_Meta_Birlestirme?
      ClampValue(AI_Meta_Agirlik*(0.55+0.45*lastAIRegimeStability),0.08,0.38):0.0;
   double rawProbability=(1.0-metaWeight)*baseProbability+
                         metaWeight*lastAIMetaProbability;

   lastAIConsensus=ClampValue((deepWeight*deepConsensus+
                               microWeight*microConsensus)/networkWeightTotal,
                              0.50,1.0);
   lastAIFusionQuality=ClampValue(0.34*lastAIDeepReliability+
                                  0.34*lastAIMicroReliability+
                                  0.12*lastMemoryConfidence+
                                  0.20*lastAIRegimeStability,0.0,1.0);

   double totalDisagreement=(deepWeight*lastAIDisagreement+
                             microWeight*lastMicroDisagreement)/networkWeightTotal;
   double crossModelGap=MathAbs(deepProbability-microProbability);
   double temporalGap=MathAbs(networkProbability-lastAITemporalPrior);
   double metaGap=MathAbs(baseProbability-lastAIMetaProbability);
   double timeframeGap=MathAbs(lastAITemporalPrior-mtfPrior);
   double hierarchyGap=MathAbs(networkProbability-lastAIHierarchicalPrior);
   lastAIUncertainty=ClampValue(0.25*totalDisagreement+
                                0.17*crossModelGap+
                                0.14*temporalGap+
                                0.12*metaGap+
                                0.08*timeframeGap+
                                0.12*hierarchyGap+
                                0.12*lastAIDriftScore,0.0,1.0);
   lastAIHorizonEntropy=ClampValue(1.0-
      (0.55*lastAIRegimeConsensus+0.45*lastAIRegimeStability),0.0,1.0);

   double experience=ClampValue((double)aiTrainingCount/10000.0,0.15,1.0);
   lastAIEntropyConfidence=AIEntropyConfidence(rawProbability);
   double uncertaintyPenalty=MathMax(0.20,AI_Belirsizlik_Cezasi);
   double driftPenalty=AI_Drift_Farkindalik?
                       ClampValue(AI_Drift_Cezasi,0.0,1.0)*lastAIDriftScore:0.0;
   double reliability=ClampValue(0.10+0.27*lastAIConsensus+
                                 0.16*experience+
                                 0.20*lastAIFusionQuality+
                                 0.11*lastAIRegimeConsensus+
                                 0.10*lastAIRegimeStability+
                                 0.12*lastAISpecialistConsensus+
                                 0.10*lastAIEntropyConfidence-
                                 uncertaintyPenalty*lastAIUncertainty-
                                 driftPenalty,
                                 0.06,1.0);

   if(AI_Guven_Kalibrasyonu)
      lastAIProbability=0.50+(rawProbability-0.50)*reliability;
   else
      lastAIProbability=rawProbability;

   lastAIProbability=ClampValue(lastAIProbability,0.000001,0.999999);
   lastAIScore=2.0*lastAIProbability-1.0;
   lastAIConfidence=ClampValue(
      MathMax(lastAIProbability,1.0-lastAIProbability)-
      lastAIUncertainty*(1.0-memoryWeight)+
      0.12*(lastAIConsensus-0.50)+
      0.10*lastMemoryConfidence+
      0.05*(lastAIRegimeConsensus-0.50)+
      0.07*(lastAIRegimeStability-0.50)+
      0.08*(lastAISpecialistConsensus-0.50)+
      0.06*lastAIEntropyConfidence-
      0.10*lastAIDriftScore,
      0.50,1.0);
   lastAISmartWeight=AISmartDecisionWeight();
   return MathIsValidNumber(lastAIProbability);
}

bool ManageOppositePositions(int newDirection)
{
   if(!InpSingleDirection)
      return true;

   bool oppositeRemains=false;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !IsOurSelectedPosition())
         continue;

      long type=PositionGetInteger(POSITION_TYPE);
      bool opposite=(newDirection>0 && type==POSITION_TYPE_SELL) ||
                    (newDirection<0 && type==POSITION_TYPE_BUY);

      if(!opposite)
         continue;

      double profit=PositionGetDouble(POSITION_PROFIT)+
                    PositionGetDouble(POSITION_SWAP);

      bool mayClose=InpCloseOppositeProfit &&
                    profit>=MathMax(0.01,InpMinimumCloseProfit);

      if(mayClose)
      {
         if(!trade.PositionClose(ticket))
            oppositeRemains=true;
      }
      else
      {
         oppositeRemains=true;
      }
   }

   if(oppositeRemains)
      lastStatus="TERS POZISYON ZARARDA - YENI YON BEKLIYOR";

   return !oppositeRemains;
}

bool MediumVolatilityAllowed(double currentATR)
{
   if(!InpMediumVolatilityOnly)
   {
      lastVolatilityPercentile=50.0;
      lastVolatilityRatio=1.0;
      return true;
   }

   int lookback=MathMax(50,MathMin(1000,InpVolatilityLookback));
   double atrValues[];
   ArrayResize(atrValues,lookback);
   int copied=CopyBuffer(hATR,0,1,lookback,atrValues);

   if(copied<50 || currentATR<=0.0)
   {
      lastStatus="ORTA VOLATILITE ICIN ATR VERISI BEKLENIYOR";
      return false;
   }

   ArrayResize(atrValues,copied);
   int atOrBelow=0;
   for(int i=0;i<copied;i++)
   {
      if(atrValues[i]<=currentATR)
         atOrBelow++;
   }

   lastVolatilityPercentile=100.0*(double)atOrBelow/copied;
   ArraySort(atrValues);
   double medianATR=atrValues[copied/2];
   lastVolatilityRatio=SafeDivide(currentATR,MathMax(EnginePoint(),medianATR));

   double minimumPercentile=MathMin(InpMediumVolMinPercentile,
                                    InpMediumVolMaxPercentile);
   double maximumPercentile=MathMax(InpMediumVolMinPercentile,
                                    InpMediumVolMaxPercentile);
   double minimumRatio=MathMin(InpMediumVolMinRatio,InpMediumVolMaxRatio);
   double maximumRatio=MathMax(InpMediumVolMinRatio,InpMediumVolMaxRatio);

   if(lastVolatilityPercentile<minimumPercentile ||
      lastVolatilityRatio<minimumRatio)
   {
      lastStatus="VOLATILITE DUSUK - ORTA SEVIYE BEKLENIYOR";
      return false;
   }

   if(lastVolatilityPercentile>maximumPercentile ||
      lastVolatilityRatio>maximumRatio)
   {
      lastStatus="VOLATILITE YUKSEK - ORTA SEVIYE BEKLENIYOR";
      return false;
   }

   return true;
}

int EvaluateStrategy()
{
   if(!IsForexSymbol())
   {
      lastStatus="SADECE FOREX PARITELERI";
      return 0;
   }

   int target=MathMax(1,InpMaxOpenTrades);
   if(CountAllBotTrades()>=target)
   {
      lastStatus="HEDEF ISLEM ADEDI TAMAM - TEK PARITE SEPET";
      return 0;
   }

   if(SymbolHasBotPosition(EngineSymbol()))
   {
      lastStatus="BU PARITEDE BOT POZISYONU ZATEN ACIK";
      return 0;
   }

   if(!CheckSpread())
      return 0;

   double fast=GetBufferedValue(hFastMA,1);
   double slow=GetBufferedValue(hSlowMA,1);
   double atr=GetBufferedValue(hATR,1);
   double rsi=GetBufferedValue(hRSI,1);

   if(atr>0.0)
      lastATR=atr;

   LiveCandleDirection();

   if(CurrentBreakoutBlocked())
   {
      lastStatus="KIRILMA ALGILANDI - YENI ISLEM YOK | GUC "+
                 DoubleToString(lastBreakoutStrength,2);
      return 0;
   }

   int candleAge=-1;
   LiveCandleColorFirstSeconds(EngineSymbol(),candleAge);
   lastLiveEntryAgeSeconds=candleAge;

   if(candleAge<0)
   {
      lastStatus="M15 CANLI MUM ZAMANI BEKLENIYOR";
      return 0;
   }

   if(!InpContinuousEntryAnyTime &&
      candleAge>MathMax(1,InpEntryFirstSeconds))
   {
      lastStatus="M15 ILK "+IntegerToString(InpEntryFirstSeconds)+" SN BEKLENIYOR";
      return 0;
   }

   int emaDirection=EMA42TrendDirection();
   if(emaDirection==0)
   {
      lastStatus="EMA42 YATAY - BUY/SELL YOK";
      return 0;
   }

   int liveCandleDirection=CurrentLiveCandleColorDirection(EngineSymbol());
   if(liveCandleDirection==0)
   {
      lastStatus="M15 MUM DOJI/YONSUZ - ISLEM YOK";
      return 0;
   }

   if(liveCandleDirection!=emaDirection)
   {
      lastStatus="EMA42 + M15 MUM YONU UYUSMUYOR - ISLEM YOK";
      return 0;
   }

   double entryDistancePoints=0.0;
   if(!CandleOpenDistanceReached(EngineSymbol(),emaDirection,entryDistancePoints))
   {
      lastStatus="M15 MUM ACILISINDAN "+
                 DoubleToString(InpEntryDistancePoints,1)+
                 " POINT BEKLENIYOR | SU AN "+
                 DoubleToString(entryDistancePoints,1);
      return 0;
   }

   int candleDirection=emaDirection;

   MqlRates mhBars[];
   ArraySetAsSeries(mhBars,true);
   int mhNeeded=AI_MULTI_HORIZONS+25;
   lastMultiHorizonScore=0.0;
   lastMultiHorizonAgreement=0.0;
   if(CopyRates(EngineSymbol(),InpTF,0,mhNeeded,mhBars)>=mhNeeded)
      lastMultiHorizonScore=MultiHorizonDirectionScore(mhBars,1,
                                                       AI_MULTI_HORIZONS,
                                                       lastMultiHorizonAgreement);

   double liveRegimeDirection=0.0;
   if(ArraySize(mhBars)>=AI_MULTI_HORIZONS+2)
      lastAIRegimeStability=AIRegimeStabilityFromRates(mhBars,1,liveRegimeDirection);

   bool indicatorsReady=false;
   if(rsi>0.0)
      indicatorsReady=UpdateRSIBollingerScore(rsi);

   // 10K mikro-ag + derin ensemble AKTIF kullanilir; canli mum rengini kilitlemez.
   // AI guveni secim ve kalite puanina katilir.
   bool liveAIReady=UpdateDeepAI((double)candleDirection*0.50);
   double aiDirectionalConfidence=0.50;
   if(liveAIReady && candleDirection!=0)
      aiDirectionalConfidence=candleDirection>0?
                              lastAIProbability:(1.0-lastAIProbability);

   if(candleDirection!=0)
   {
      double mhAlignment=ClampValue(candleDirection*lastMultiHorizonScore,-1.0,1.0);
      double quality=0.60+0.22*aiDirectionalConfidence+
                     0.18*ClampValue(0.50+0.50*mhAlignment,0.0,1.0);
      lastFinalScore=candleDirection*quality;
   }
   else if(liveAIReady)
      lastFinalScore=lastAIScore;

   if(InpSignalMode==SIGNAL_LIVE_CANDLE)
   {
      if(candleDirection==0)
         lastStatus="MUM RENGI BEKLENIYOR VEYA ILK "+IntegerToString(InpEntryFirstSeconds)+" SN GECTI";
      else
      {
         lastDirectionSource=candleDirection>0?
                             "CANLI MUM YESIL -> BUY":
                             "CANLI MUM KIRMIZI -> SELL";
         lastStatus="ILK "+IntegerToString(lastLiveEntryAgeSeconds)+" SN | "+lastDirectionSource+
                    " | AI "+DoubleToString(aiDirectionalConfidence*100.0,1)+"%"+
                    " | UFUK "+DoubleToString(lastMultiHorizonScore,2)+
                    " | STAB "+DoubleToString(lastAIRegimeStability*100.0,0)+"%";
      }
      return candleDirection;
   }

   if(atr<=0.0)
   {
      lastStatus="ATR VERISI BEKLENIYOR";
      return 0;
   }

   if(!MediumVolatilityAllowed(atr))
      return 0;

   bool strategiesReady=true;
   if(InpUse3000Strategies)
      strategiesReady=Build3000Strategies();

   bool directReady=true;
   if(InpUseDirect900)
      directReady=Build900DirectStrategies(fast,slow,rsi,candleDirection);

   bool advancedReady=true;
   if(InpUseAdvanced100)
      advancedReady=Build100AdvancedStrategies();

   double advancedWeight=ClampValue(InpAdvanced100Weight,0.0,1.0);
   double directAndAdvancedScore=lastDirectScore;
   if(advancedReady && InpUseAdvanced100)
   {
      if(directReady && InpUseDirect900)
         directAndAdvancedScore=(1.0-advancedWeight)*lastDirectScore+
                                advancedWeight*lastAdvancedScore;
      else
         directAndAdvancedScore=lastAdvancedScore;
   }

   bool aiReady=UpdateDeepAI(directAndAdvancedScore);

   double technicalScore=0.0;
   if(fast>slow) technicalScore+=0.50;
   else if(fast<slow) technicalScore-=0.50;

   if(indicatorsReady)
      technicalScore+=0.50*lastIndicatorScore;

   double strategyContribution=0.0;
   if(strategiesReady && InpUse3000Strategies)
      strategyContribution=lastStrategyScore*ClampValue(InpStrategyWeight,0.0,1.0);

   double directContribution=0.0;
   if(directReady && InpUseDirect900)
      directContribution=lastDirectScore*ClampValue(InpDirectWeight,0.0,1.0);

   double advancedContribution=0.0;
   if(advancedReady && InpUseAdvanced100)
      advancedContribution=lastAdvancedScore*advancedWeight;

   double aiContribution=0.0;
   if(aiReady && AI_Derin_Ogrenme)
      aiContribution=lastAIScore*lastAISmartWeight;

   lastFinalScore=technicalScore+strategyContribution+
                  directContribution+advancedContribution+aiContribution;

   if(InpSignalMode==SIGNAL_DIRECT_900_ONLY)
   {
      if(!directReady || !InpUseDirect900)
      {
         if(InpCandleFallback)
         {
            lastStatus="900 STRATEJI HAZIR DEGIL - MUM YONU KULLANILDI";
            return candleDirection;
         }
         return 0;
      }

      if(InpRequireAgreement && lastDirectAgreement<InpMinAgreement)
      {
         if(InpCandleFallback)
         {
            lastStatus="900 OY MUTABAKATI DUSUK - MUM YONU KULLANILDI";
            return candleDirection;
         }
         lastStatus="900 DIREKT STRATEJI MUTABAKATI BEKLENIYOR";
         return 0;
      }

      int voteLead=MathAbs(lastDirectBuyVotes-lastDirectSellVotes);
      if(voteLead<MathMax(1,InpDirectMinVoteLead) ||
         lastDirectBuyVotes==lastDirectSellVotes)
      {
         if(InpCandleFallback)
         {
            lastStatus="900 OY BERABERE - MUM YONU KULLANILDI";
            return candleDirection;
         }
         lastStatus="900 DIREKT STRATEJI OY FARKI BEKLENIYOR";
         return 0;
      }

      if(lastDirectBuyVotes>lastDirectSellVotes)
      {
         lastStatus="900 DIREKT STRATEJI BUY COGUNLUGU";
         return 1;
      }

      lastStatus="900 DIREKT STRATEJI SELL COGUNLUGU";
      return -1;
   }

   if(InpSignalMode==SIGNAL_AI_DEEP_ONLY)
   {
      double minimumConfidence=ClampValue(AI_Min_Guven,0.50,0.99);
      if(aiReady && lastAIConfidence>=minimumConfidence)
      {
         if(lastAIProbability>=0.50)
         {
            lastStatus="DERIN AI BUY TAHMINI";
            return 1;
         }

         lastStatus="DERIN AI SELL TAHMINI";
         return -1;
      }

      lastStatus="DERIN AI GUVEN BEKLIYOR - MUM YONU KULLANILDI";
      return InpCandleFallback?candleDirection:0;
   }

   if(InpSignalMode==SIGNAL_DIRECT_900_AI)
   {
      if(!directReady && !advancedReady && !aiReady)
      {
         lastStatus="1000 STRATEJI + AI VERI BEKLIYOR";
         return InpCandleFallback?candleDirection:0;
      }

      double aiWeight=lastAISmartWeight;
      double combinedScore=directAndAdvancedScore;
      double minimumConfidence=ClampValue(AI_Min_Guven,0.50,0.99);

      if(aiReady && lastAIConfidence>=minimumConfidence)
         combinedScore=(1.0-aiWeight)*combinedScore+aiWeight*lastAIScore;

      if(indicatorsReady)
         combinedScore=0.75*combinedScore+0.25*lastIndicatorScore;

      if(combinedScore>0.02)
      {
         lastStatus="1000 STRATEJI + DERIN AI BUY";
         return 1;
      }

      if(combinedScore<-0.02)
      {
         lastStatus="1000 STRATEJI + DERIN AI SELL";
         return -1;
      }

      lastStatus="1000 + AI BERABERE - MUM YONU KULLANILDI";
      return InpCandleFallback?candleDirection:0;
   }

   if(InpSignalMode==SIGNAL_STRATEGY_3000_ONLY)
   {
      if(!strategiesReady || !InpUse3000Strategies)
         return InpCandleFallback?candleDirection:0;

      if(InpRequireAgreement && lastAgreement<InpMinAgreement)
      {
         lastStatus="3000 STRATEJI MUTABAKATI BEKLENIYOR";
         return InpCandleFallback?candleDirection:0;
      }

      if(lastStrategyScore>=InpMinSignalStrength)
      {
         lastStatus="3000 STRATEJI BUY SINYALI";
         return 1;
      }

      if(lastStrategyScore<=-InpMinSignalStrength)
      {
         lastStatus="3000 STRATEJI SELL SINYALI";
         return -1;
      }

      lastStatus="3000 STRATEJI GUCU BEKLENIYOR";
      return InpCandleFallback?candleDirection:0;
   }

   if(!strategiesReady || !directReady)
   {
      lastStatus="TUM MOTORLAR VERI BEKLIYOR";
      return InpCandleFallback?candleDirection:0;
   }

   if(lastFinalScore>=InpMinSignalStrength)
   {
      lastStatus="4000 OY + DERIN AI BUY SINYALI";
      return 1;
   }

   if(lastFinalScore<=-InpMinSignalStrength)
   {
      lastStatus="4000 OY + DERIN AI SELL SINYALI";
      return -1;
   }

   lastStatus="4000 OY + AI ZAYIF - MUM YONU KULLANILDI";
   return InpCandleFallback?candleDirection:0;
}

void NormalizeStops(int direction,double entry,double &sl,double &tp)
{
   int stopLevel=(int)SymbolInfoInteger(EngineSymbol(),SYMBOL_TRADE_STOPS_LEVEL);
   double minimumDistance=MathMax(0,stopLevel)*EnginePoint();

   if(sl>0.0)
   {
      if(direction>0 && entry-sl<minimumDistance)
         sl=entry-minimumDistance;
      if(direction<0 && sl-entry<minimumDistance)
         sl=entry+minimumDistance;
      sl=NormalizeDouble(sl,EngineDigits());
   }

   if(tp>0.0)
   {
      if(direction>0 && tp-entry<minimumDistance)
         tp=entry+minimumDistance;
      if(direction<0 && entry-tp<minimumDistance)
         tp=entry-minimumDistance;
      tp=NormalizeDouble(tp,EngineDigits());
   }
}

int SecondsOfDay(datetime value)
{
   MqlDateTime part;
   TimeToStruct(value,part);
   return part.hour*3600+part.min*60+part.sec;
}

bool BrokerMarketSessionOpen()
{
   // V67: Fail-open yok. Kapali seans, eski tick veya eksik seans verisi
   // yeni emri bloke eder.
   return StrictMarketOpenForSymbol(EngineSymbol());
}

bool TradingAllowed(int direction)
{
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
   {
      lastStatus="TERMINAL BAGLANTISI YOK";
      return false;
   }

   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ||
      !MQLInfoInteger(MQL_TRADE_ALLOWED) ||
      !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
   {
      lastStatus="ALGORITMIK ISLEM IZNI KAPALI";
      return false;
   }

   long tradeMode=SymbolInfoInteger(EngineSymbol(),SYMBOL_TRADE_MODE);

   if(tradeMode==SYMBOL_TRADE_MODE_DISABLED ||
      tradeMode==SYMBOL_TRADE_MODE_CLOSEONLY)
   {
      lastStatus="SEMBOL YENI ISLEME KAPALI";
      return false;
   }

   if(direction>0 && tradeMode==SYMBOL_TRADE_MODE_SHORTONLY)
   {
      lastStatus="SEMBOL SADECE SELL ISLEME ACIK";
      return false;
   }

   if(direction<0 && tradeMode==SYMBOL_TRADE_MODE_LONGONLY)
   {
      lastStatus="SEMBOL SADECE BUY ISLEME ACIK";
      return false;
   }

   if(!BrokerMarketSessionOpen())
   {
      lastStatus="PIYASA KAPALI / SEANS KAPALI / FIYAT BAYAT - EMIR YOK";
      return false;
   }

   // Emir gondermeden hemen once ikinci kez taze tick dogrula.
   MqlTick liveTick;
   if(!FreshTradableMarketTick(EngineSymbol(),liveTick))
   {
      lastStatus="PIYASA KAPALI VEYA GUNCEL FIYAT YOK - EMIR YOK";
      return false;
   }

   return true;
}


int EMA42TrendDirection()
{
   if(!InpUseEMA42TrendFilter)
      return 0;

   if(hTrendEMA==INVALID_HANDLE)
      return 0;

   double ema[];
   ArraySetAsSeries(ema,true);
   if(CopyBuffer(hTrendEMA,0,0,2,ema)<2)
      return 0;

   double point=SymbolInfoDouble(EngineSymbol(),SYMBOL_POINT);
   if(point<=0.0)
      point=0.00001;

   double minSlope=MathMax(0.0,InpEMA42MinSlopePoints)*point;
   double slope=ema[0]-ema[1];

   if(slope>minSlope)
      return 1;
   if(slope<-minSlope)
      return -1;

   return 0;
}

void ExecuteTrade(int direction)
{
   if(direction==0 || !TradingAllowed(direction))
      return;

   // V91: Emirden hemen once EMA42 egimi + canli M15 mum rengini tekrar dogrula.
   if(InpUseEMA42TrendFilter)
   {
      int ema30Direction=EMA42TrendDirection();
      int candleColorDirection=CurrentLiveCandleColorDirection(EngineSymbol());

      if(ema30Direction==0 || candleColorDirection==0 ||
         ema30Direction!=direction || candleColorDirection!=direction)
      {
         lastStatus="EMA42 + M15 MUM YONU UYUSMUYOR - EMIR YOK";
         return;
      }

      double finalEntryDistancePoints=0.0;
      if(!CandleOpenDistanceReached(EngineSymbol(),direction,finalEntryDistancePoints))
      {
         lastStatus="8 POINT GIRIS MESAFESI HENUZ YOK - EMIR YOK";
         return;
      }
   }

   if(gBasketOrderLock)
      return;

   int strictTarget=MathMax(1,InpMaxOpenTrades);
   if(gBasketOrdersOpened>=strictTarget)
   {
      lastStatus="BU SEPETTE ISLEM ADEDI TAMAM: "+IntegerToString(strictTarget);
      return;
   }

   if(CurrentBreakoutBlocked())
   {
      lastStatus="KIRILMA VAR - EMIR GONDERILMEDI | GUC "+
                 DoubleToString(lastBreakoutStrength,2);
      return;
   }

   int target=strictTarget;
   if(gBasketOrdersOpened>=target)
   {
      lastStatus="SEPET HEDEFI TAMAM: "+IntegerToString(target)+" EMIR";
      return;
   }

   if(!ExclusiveSymbolLockValid())
      return;

   double buyRSIMinimum=50.0;
   double buyRSIMaximum=70.0;
   double sellRSIMinimum=30.0;
   double sellRSIMaximum=50.0;

   bool rsiAllowed=true;
   if(InpUseRSI && direction>0)
      rsiAllowed=lastRSI>=buyRSIMinimum && lastRSI<=buyRSIMaximum;
   else if(InpUseRSI && direction<0)
      rsiAllowed=lastRSI>=sellRSIMinimum && lastRSI<=sellRSIMaximum;

   lastRSIDirectionalIdeal=rsiAllowed;

   if(InpRequireIndicatorAgreement &&
      MathAbs(lastIndicatorScore)>0.01 &&
      direction*lastIndicatorScore<0.0)
   {
      lastStatus="RSI/BOLLINGER YON ONAYI BEKLENIYOR";
      return;
   }

   if(!ManageOppositePositions(direction))
      return;

   datetime currentBar=iTime(EngineSymbol(),InpTF,0);
   if(!InpContinuousOpen && currentBar>0 && currentBar==lastSingleEntryBar)
   {
      lastStatus="BU MUMDA GIRIS YAPILDI - YENI MUM BEKLENIYOR";
      return;
   }

   ulong now=GetTickCount64();
   if(now-lastEntryMs<(ulong)MathMax(0,InpCooldownMilliseconds))
      return;

   MqlTick tick;
   if(!SymbolInfoTick(EngineSymbol(),tick))
   {
      lastStatus="GECERLI FIYAT YOK";
      return;
   }

   double entry=direction>0?tick.ask:tick.bid;
   double sl=0.0;
   double tp=0.0;

   int stopLossPoints=MathMax(0,InpStopLossPoints);
   if(stopLossPoints>0)
      sl=direction>0?entry-stopLossPoints*EnginePoint():
                     entry+stopLossPoints*EnginePoint();

   if(InpUseDynamicTP && lastATR>0.0)
      tp=direction>0?entry+lastATR*InpTPMultiplier:
                     entry-lastATR*InpTPMultiplier;

   NormalizeStops(direction,entry,sl,tp);

   double requestedLot=InpBaseLot;
   if(InpUseBrokerMinimumLot)
   {
      double brokerMinimumLot=SymbolInfoDouble(EngineSymbol(),SYMBOL_VOLUME_MIN);
      if(brokerMinimumLot>0.0)
         requestedLot=brokerMinimumLot;
   }
   double lot=NormalizeLot(requestedLot);

   ResetLastError();
   bool sent=false;
   gBasketOrderLock=true;

   trade.SetTypeFillingBySymbol(EngineSymbol());
   if(direction>0)
      sent=trade.Buy(lot,EngineSymbol(),0.0,sl,tp,InpCommentTag);
   else
      sent=trade.Sell(lot,EngineSymbol(),0.0,sl,tp,InpCommentTag);

   uint retcode=trade.ResultRetcode();
   gBasketOrderLock=false;
   bool accepted=sent &&
                 (retcode==TRADE_RETCODE_DONE ||
                  retcode==TRADE_RETCODE_PLACED ||
                  retcode==TRADE_RETCODE_DONE_PARTIAL);

   if(accepted)
   {
      double fillPrice=trade.ResultPrice();
      if(fillPrice>0.0)
      {
         lastExecutionSlippage=MathAbs(fillPrice-entry)/EnginePoint();
         if(averageExecutionSlippage<=0.0)
            averageExecutionSlippage=lastExecutionSlippage;
         else
            averageExecutionSlippage=0.90*averageExecutionSlippage+
                                     0.10*lastExecutionSlippage;
      }

      gBasketOrdersOpened++;
      lastEntryMs=now;
      lastSingleEntryBar=currentBar;
      gLastOpenedSymbol=EngineSymbol();
      lastStatus=(direction>0?"BUY":"SELL")+" ACILDI: "+EngineSymbol()+
                 " | YEREL "+(direction>0?"DIP":"TEPE")+
                 " + "+IntegerToString(gSelectedStreakCount)+" MUM ONAY";
   }
   else
   {
      lastStatus="EMIR REDDEDILDI: "+trade.ResultRetcodeDescription()+
                 " | "+IntegerToString((int)retcode)+
                 " | "+IntegerToString(GetLastError());
      Print(lastStatus);
   }
}

void FillPositionsContinuously(int direction)
{
   if(direction==0 || continuousFillBusy)
      return;

   continuousFillBusy=true;
   int target=MathMax(1,InpMaxOpenTrades);
   int attempts=0;
   int maximumAttempts=MathMax(target*3,6);

   // V68: "Islem Adeti" kabul edilen emir/deal sayisidir.
   // Hedging hesapta bunlar ayri pozisyon gorunur.
   // Netting hesapta broker ayni semboldeki emirleri tek net pozisyonda birlestirir.
   while(gBasketOrdersOpened<target && attempts<maximumAttempts)
   {
      int beforeOrders=gBasketOrdersOpened;
      ExecuteTrade(direction);
      attempts++;

      if(gBasketOrdersOpened<=beforeOrders)
      {
         // Emir reddedildiyse ayni dongude sonsuz tekrar yapma.
         break;
      }
   }

   if(gBasketOrdersOpened>=target)
   {
      gBasketEntryComplete=true;
      lastStatus="SEPET TAMAM: "+EngineSymbol()+" | "+
                 IntegerToString(target)+" ADET "+
                 (direction>0?"BUY":"SELL")+
                 (IsHedgingAccount()?" | HEDGING":" | NETTING-BIRLESIK");
   }
   else
   {
      lastStatus="SEPET DOLDURULUYOR: "+EngineSymbol()+" | EMIR "+
                 IntegerToString(gBasketOrdersOpened)+"/"+
                 IntegerToString(target);
   }

   continuousFillBusy=false;
}

bool DrawdownAllowed()
{
   if(!InpMaxDrawdownGuard)
      return true;

   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   double balance=AccountInfoDouble(ACCOUNT_BALANCE);

   if(balance<=0.0)
      return true;

   double drawdown=(balance-equity)/balance*100.0;
   if(drawdown>=InpMaxDrawdownPct)
   {
      lastStatus="DRAWDOWN KORUMASI: "+DoubleToString(drawdown,2)+"%";
      return false;
   }

   return true;
}

datetime BrokerServerTime()
{
   datetime now=TimeTradeServer();
   if(now<=0)
      now=TimeCurrent();
   return now;
}

int MinuteOfDay(const MqlDateTime &timePart)
{
   return timePart.hour*60+timePart.min;
}

bool IsFridayClosingTime()
{
   MqlDateTime timePart;
   TimeToStruct(BrokerServerTime(),timePart);

   int closeMinute=MathMax(0,MathMin(23,InpFridayCloseHour))*60+
                   MathMax(0,MathMin(59,InpFridayCloseMinute));

   return timePart.day_of_week==5 && MinuteOfDay(timePart)>=closeMinute;
}

bool WeeklyEntryWindowOpen()
{
   if(!InpUseWeeklySchedule)
      return true;

   MqlDateTime timePart;
   TimeToStruct(BrokerServerTime(),timePart);

   int currentMinute=MinuteOfDay(timePart);
   int mondayOpen=MathMax(0,MathMin(23,InpMondayOpenHour))*60+
                  MathMax(0,MathMin(59,InpMondayOpenMinute));
   int fridayClose=MathMax(0,MathMin(23,InpFridayCloseHour))*60+
                   MathMax(0,MathMin(59,InpFridayCloseMinute));

   if(timePart.day_of_week==0 || timePart.day_of_week==6)
      return false;

   if(timePart.day_of_week==1 && currentMinute<mondayOpen)
      return false;

   if(timePart.day_of_week==5 && currentMinute>=fridayClose)
      return false;

   return true;
}

double BasketProfit()
{
   double total=0.0;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;

      total+=PositionGetDouble(POSITION_PROFIT)+
             PositionGetDouble(POSITION_SWAP);
   }

   return total;
}

bool SuccessfulCloseRetcode()
{
   uint retcode=trade.ResultRetcode();
   return retcode==TRADE_RETCODE_DONE ||
          retcode==TRADE_RETCODE_DONE_PARTIAL;
}

bool ClosePositionForSingleTP(ulong ticket)
{
   if(!PositionSelectByTicket(ticket))
      return true;

   string positionSymbol=PositionGetString(POSITION_SYMBOL);
   trade.SetTypeFillingBySymbol(positionSymbol);

   ResetLastError();
   bool requestAccepted=trade.PositionClose(
      ticket,
      (ulong)MathMax(0,InpDeviationPoints)
   );
   bool closed=requestAccepted && SuccessfulCloseRetcode();

   if(!closed)
   {
      Print("Automatic single-position TP close failed. Ticket: ",ticket,
            " symbol: ",positionSymbol,
            " retcode: ",trade.ResultRetcode(),
            " description: ",trade.ResultRetcodeDescription(),
            " error: ",GetLastError());
   }

   if(IsForexSymbolName(EngineSymbol()))
      trade.SetTypeFillingBySymbol(EngineSymbol());

   return closed;
}

bool CloseAllBotPositionsFastPeak()
{
   bool allClosed=true;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;

      string symbol=PositionGetString(POSITION_SYMBOL);
      trade.SetTypeFillingBySymbol(symbol);
      ResetLastError();
      bool ok=trade.PositionClose(ticket,(ulong)MathMax(0,InpDeviationPoints));
      if(!ok || !SuccessfulCloseRetcode())
      {
         allClosed=false;
         Print("Peak-profit close failed: ",ticket," ",symbol," ",
               trade.ResultRetcodeDescription()," error=",GetLastError());
      }
   }

   if(IsForexSymbolName(EngineSymbol()))
      trade.SetTypeFillingBySymbol(EngineSymbol());

   return allClosed && CountAllBotTrades()==0;
}

bool ManageBasketTakeProfit()
{
   lastBasketProfit=BasketProfit();
   int openTrades=CountAllBotTrades();
   ulong nowMs=GetTickCount64();

   if(openTrades<=0)
   {
      basketTakeProfitClosing=false;
      lastBasketProfit=0.0;
      gBasketPeakProfit=0.0;
      gBasketPeakGiveback=0.0;
      gPeakProfitArmed=false;
      gProfitVelocityEma=0.0;
      gPreviousProfitVelocity=0.0;
      gPreviousBasketProfit=0.0;
      gDynamicPeakGivebackPct=0.0;
      gPreviousProfitSampleMs=0;
      gLastAIProfitEvalMs=0;
      gAIProfitDirectionConfidence=0.50;
      gAIProfitReversal=false;
      return true;
   }

   // V91 - DIREKT PARA CINSINDEN KAR AL
   // Ornek: Kari_Al_Para=2.00 ise sepetin toplam acik kari
   // 2.00 hesap para birimine ulasir ulasmaz tum EA pozisyonlarini kapat.
   if(InpAutoTakeProfit && Kari_Al_Para>0.0 &&
      lastBasketProfit>=Kari_Al_Para)
   {
      if(nowMs-lastProfitCloseMs<75)
         return false;

      lastProfitCloseMs=nowMs;
      basketTakeProfitClosing=true;

      double moneyTargetCloseProfit=lastBasketProfit;
      bool moneyClosed=CloseAllBotPositionsFastPeak();
      basketTakeProfitClosing=false;

      if(moneyClosed)
      {
         gBasketEntryComplete=true;
         gFastRefillAfterFlat=InpContinuousTrading;
         gNeedSymbolScan=true;
         lastBasketProfit=0.0;
         lastStatus="PARA KAR AL KAPANDI: "+
                    DoubleToString(moneyTargetCloseProfit,2)+
                    " / HEDEF "+
                    DoubleToString(Kari_Al_Para,2);
         return false;
      }

      lastStatus="PARA KAR AL KAPATMA DEVAM EDIYOR";
      return false;
   }

   if(!InpAutoTakeProfit || Kari_Al_Para<=0.0)
   {
      basketTakeProfitClosing=false;
      return true;
   }

   // ---------------------------------------------------------------
   // V71 ADAPTIVE MAX PROFIT CAPTURE
   // Tam gelecekteki zirve bilinemez. Sistem mevcut zirveyi tick/timer bazinda
   // izler ve kâr momentumu gucluyken kosmaya izin verir; momentum zayiflarsa
   // toleransi otomatik daraltir.
   // ---------------------------------------------------------------
   double instantVelocity=0.0;
   if(gPreviousProfitSampleMs>0 && nowMs>gPreviousProfitSampleMs)
   {
      double dt=(double)(nowMs-gPreviousProfitSampleMs)/1000.0;
      if(dt>0.0)
         instantVelocity=(lastBasketProfit-gPreviousBasketProfit)/dt;

      if(gPreviousProfitSampleMs==0)
         gProfitVelocityEma=instantVelocity;
      else
         gProfitVelocityEma=0.72*gProfitVelocityEma+0.28*instantVelocity;
   }

   double acceleration=gProfitVelocityEma-gPreviousProfitVelocity;
   gPreviousProfitVelocity=gProfitVelocityEma;
   gPreviousBasketProfit=lastBasketProfit;
   gPreviousProfitSampleMs=nowMs;

   if(lastBasketProfit>gBasketPeakProfit)
      gBasketPeakProfit=lastBasketProfit;

   // V74 AI MAX-PROFIT:
   // Acik sepet varken 10K AI'yi belirli araliklarla yenile.
   // AI mevcut sepet yonune guvenini kaybederse, zirveden kucuk bir geri cekilme
   // ile birlikte kâr cikisini hizlandir.
   if(InpAI_MaxProfitExit && gBasketDirection!=0 &&
      nowMs-gLastAIProfitEvalMs>=(ulong)MathMax(100,InpAI_ProfitEvalMs))
   {
      gLastAIProfitEvalMs=nowMs;
      bool aiProfitReady=UpdateDeepAI((double)gBasketDirection*0.35);

      if(aiProfitReady)
      {
         gAIProfitDirectionConfidence=
            gBasketDirection>0 ? lastAIProbability : (1.0-lastAIProbability);

         double threshold=ClampValue(InpAI_ExitConfidence,0.50,0.95);
         gAIProfitReversal=(lastAIConfidence>=threshold &&
                            gAIProfitDirectionConfidence<(1.0-threshold));
      }
   }

   if(InpFastPeakProfitLock)
   {
      double armProfit=MathMax(0.01,Kari_Al_Para);
      if(gBasketPeakProfit>=armProfit)
         gPeakProfitArmed=true;

      if(gPeakProfitArmed)
      {
         double minPct=ClampValue(InpPeakMinGivebackPct,0.2,40.0);
         double maxPct=ClampValue(InpPeakMaxGivebackPct,minPct,60.0);
         double basePct=ClampValue(InpPeakGivebackPercent,minPct,maxPct);

         // Kâr hizi mevcut peak'e gore normalize edilir.
         double relativeVelocity=0.0;
         if(gBasketPeakProfit>0.001)
            relativeVelocity=gProfitVelocityEma/gBasketPeakProfit;

         double adaptivePct=basePct;

         if(InpAdaptiveMaxProfit)
         {
            // Cok guclu yukselis: erken cikma, zirvenin gelismesine izin ver.
            if(relativeVelocity>0.20 && acceleration>=0.0)
               adaptivePct=maxPct;
            else if(relativeVelocity>0.08)
               adaptivePct=MathMin(maxPct,MathMax(basePct,9.0));
            else if(relativeVelocity>0.015)
               adaptivePct=MathMin(maxPct,MathMax(minPct,6.0));
            // Kâr artisi durdu: peak'e daha yakin kilitle.
            else if(relativeVelocity>=0.0)
               adaptivePct=MathMax(minPct,4.0);
            else if(relativeVelocity>-0.04)
               adaptivePct=MathMax(minPct,3.0);
            else
               adaptivePct=minPct;

            // Negatif ivme varsa biraz daha sikilastir.
            if(acceleration<0.0)
               adaptivePct=MathMax(minPct,adaptivePct-1.0);
         }

         int trendNow=EMA42TrendDirection();
         int candleNow=CurrentLiveCandleColorDirection(EngineSymbol());

         if(InpExitOnEMA42CandleReversal &&
            gBasketDirection!=0 &&
            (trendNow!=gBasketDirection || candleNow!=gBasketDirection))
            adaptivePct=MathMax(0.20,MathMin(adaptivePct,0.75));

         gDynamicPeakGivebackPct=adaptivePct;

         double givebackByPct=gBasketPeakProfit*adaptivePct/100.0;
         gBasketPeakGiveback=MathMax(MathMax(0.001,InpPeakGivebackMoney),
                                     givebackByPct);

         double retreat=gBasketPeakProfit-lastBasketProfit;
         double retreatPct=(gBasketPeakProfit>0.0)?
                           (retreat/gBasketPeakProfit*100.0):0.0;

         // Kari_Al_Para tetiklendikten sonra ana tabanin buyuk bolumunu geri verme.
         double profitFloor=armProfit*
                            ClampValue(InpPeakProfitFloorPct,10.0,100.0)/100.0;

         bool normalPeakRetreat=
              lastBasketProfit>0.0 &&
              retreat>=gBasketPeakGiveback;

         // Hızlı negatif momentumda daha kucuk geri cekilmede kapat.
         bool fastMomentumReversal=
              lastBasketProfit>0.0 &&
              gProfitVelocityEma<0.0 &&
              acceleration<0.0 &&
              retreatPct>=MathMax(0.5,minPct);

         bool floorProtection=
              lastBasketProfit>0.0 &&
              gBasketPeakProfit>=armProfit &&
              lastBasketProfit<=profitFloor;

         bool aiPeakExit=
              InpAI_MaxProfitExit &&
              gAIProfitReversal &&
              lastBasketProfit>0.0 &&
              gBasketPeakProfit>=armProfit &&
              retreatPct>=MathMax(0.20,InpAI_MinPeakRetreatPct);

         int currentEMA42Direction=EMA42TrendDirection();
         int currentCandleDirection=CurrentLiveCandleColorDirection(EngineSymbol());

         bool trendPeakExit=
              InpExitOnEMA42CandleReversal &&
              lastBasketProfit>0.0 &&
              gBasketPeakProfit>=armProfit &&
              (currentEMA42Direction!=gBasketDirection ||
               currentCandleDirection!=gBasketDirection) &&
              retreatPct>=MathMax(0.05,InpTrendReversalMinRetreatPct);

         double ultraRetreatMoney=MathMax(0.0,gBasketPeakProfit-lastBasketProfit);
         double ultraRetreatPct=(gBasketPeakProfit>0.0 ?
                                 ultraRetreatMoney/gBasketPeakProfit*100.0 : 0.0);

         bool ultraPeakExit=
              InpUltraPeakLock &&
              lastBasketProfit>0.0 &&
              gBasketPeakProfit>=MathMax(armProfit,InpUltraPeakMinProfit) &&
              (ultraRetreatMoney>=MathMax(0.0,InpUltraPeakRetreatMoney) ||
               ultraRetreatPct>=MathMax(0.05,InpUltraPeakRetreatPct));

         bool immediateTrendProfitExit=
              InpImmediateProfitReversalExit &&
              lastBasketProfit>0.0 &&
              gBasketPeakProfit>=MathMax(armProfit,InpUltraPeakMinProfit) &&
              (currentEMA42Direction!=gBasketDirection ||
               currentCandleDirection!=gBasketDirection);

         if(normalPeakRetreat || fastMomentumReversal ||
            floorProtection || aiPeakExit || trendPeakExit ||
            ultraPeakExit || immediateTrendProfitExit)
         {
            if(nowMs-lastProfitCloseMs<75)
               return false;

            lastProfitCloseMs=nowMs;
            basketTakeProfitClosing=true;

            double lockedProfit=lastBasketProfit;
            double peakBeforeClose=gBasketPeakProfit;
            string closeReason="ADAPTIF PEAK";
            if(fastMomentumReversal)
               closeReason="MOMENTUM DONUSU";
            if(floorProtection)
               closeReason="KAR TABANI";
            if(aiPeakExit)
               closeReason="AI ZIRVE DONUSU";
            if(trendPeakExit)
               closeReason="EMA42/MUM ZIRVE DONUSU";
            if(ultraPeakExit)
               closeReason="ULTRA ZIRVE KAR KILIDI";
            if(immediateTrendProfitExit)
               closeReason="EMA42/MUM TERS - KARI KORU";

            bool closed=CloseAllBotPositionsFastPeak();
            basketTakeProfitClosing=false;

            if(closed)
            {
               gBasketEntryComplete=true;
               gFastRefillAfterFlat=InpContinuousTrading;
               gNeedSymbolScan=true;
               lastBasketProfit=0.0;
               lastStatus="MAX KAR "+closeReason+
                          ": PEAK "+DoubleToString(peakBeforeClose,2)+
                          " -> KAPANIS "+DoubleToString(lockedProfit,2)+
                          " | TOL %"+DoubleToString(adaptivePct,1);
               return false;
            }

            lastStatus="MAX KAR KAPATMA DEVAM EDIYOR";
            return false;
         }

         lastStatus="MAX KAR TAKIP: "+DoubleToString(lastBasketProfit,2)+
                    " | PEAK "+DoubleToString(gBasketPeakProfit,2)+
                    " | TOL %"+DoubleToString(adaptivePct,1)+
                    " | HIZ "+DoubleToString(gProfitVelocityEma,4);
      }

      return true;
   }

   // Adaptive/peak modu kapaliysa klasik tek pozisyon TP.
   double targetProfit=NormalizeDouble(Kari_Al_Para,2);
   ulong bestTicket=0;
   double bestProfit=-1.0e100;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;

      double positionProfit=PositionGetDouble(POSITION_PROFIT)+
                            PositionGetDouble(POSITION_SWAP);

      if(NormalizeDouble(positionProfit,2)>=targetProfit &&
         positionProfit>bestProfit)
      {
         bestProfit=positionProfit;
         bestTicket=ticket;
      }
   }

   if(bestTicket==0)
      return true;

   if(nowMs-lastProfitCloseMs<500)
      return false;

   lastProfitCloseMs=nowMs;
   basketTakeProfitClosing=true;

   if(!ClosePositionForSingleTP(bestTicket))
   {
      basketTakeProfitClosing=false;
      return false;
   }

   basketTakeProfitClosing=false;
   lastBasketProfit=BasketProfit();
   return false;
}

bool CloseFridayPositions()
{
   ulong nowMs=GetTickCount64();
   if(nowMs-lastFridayCloseMs<1000)
      return false;

   lastFridayCloseMs=nowMs;
   bool remaining=false;
   bool closedAny=false;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;

      string positionSymbol=PositionGetString(POSITION_SYMBOL);
      trade.SetTypeFillingBySymbol(positionSymbol);

      if(trade.PositionClose(ticket))
         closedAny=true;
      else
      {
         remaining=true;
         Print("Friday close failed: ",ticket," ",positionSymbol," ",
               trade.ResultRetcodeDescription());
      }
   }

   if(IsForexSymbolName(EngineSymbol()))
      trade.SetTypeFillingBySymbol(EngineSymbol());

   if(CountAllBotTrades()>0)
      remaining=true;

   if(remaining)
      lastStatus="CUMA KAPANISI DEVAM EDIYOR";
   else if(closedAny)
      lastStatus="CUMA TUM PARITE POZISYONLARI KAPATILDI";
   else
      lastStatus="CUMA KAPANISI - ACIK POZISYON YOK";

   return !remaining;
}

bool ManageWeeklySchedule()
{
   if(!InpUseWeeklySchedule)
      return true;

   if(IsFridayClosingTime())
   {
      lastStatus="CUMA KAPANISI - POZISYONLAR KAPATILIYOR";
      CloseFridayPositions();
      return false;
   }

   if(!WeeklyEntryWindowOpen())
   {
      MqlDateTime timePart;
      TimeToStruct(BrokerServerTime(),timePart);

      if(timePart.day_of_week==0 || timePart.day_of_week==6)
         lastStatus="HAFTA SONU - PAZARTESI BEKLENIYOR";
      else if(timePart.day_of_week==1)
         lastStatus="PAZARTESI ACILIS SAATI BEKLENIYOR";
      else
         lastStatus="HAFTALIK ISLEM PENCERESI KAPALI";

      return false;
   }

   return true;
}

void ReleaseSelectedIndicators()
{
   if(hFastMA!=INVALID_HANDLE) IndicatorRelease(hFastMA);
   if(hTrendEMA!=INVALID_HANDLE) IndicatorRelease(hTrendEMA);
   if(hSlowMA!=INVALID_HANDLE) IndicatorRelease(hSlowMA);
   if(hATR!=INVALID_HANDLE) IndicatorRelease(hATR);
   if(hRSI!=INVALID_HANDLE) IndicatorRelease(hRSI);
   if(hBands!=INVALID_HANDLE) IndicatorRelease(hBands);

   hFastMA=INVALID_HANDLE;
   hTrendEMA=INVALID_HANDLE;
   hSlowMA=INVALID_HANDLE;
   hATR=INVALID_HANDLE;
   hRSI=INVALID_HANDLE;
   hBands=INVALID_HANDLE;
}

void ResetSelectedSymbolRuntime()
{
   ArrayResize(spreadSamples,0);
   spreadSampleIndex=0;
   spreadSampleCount=0;
   lastCurrentSpread=-1;
   lastMinimumSpread=-1;
   lastObservedBid=0.0;
   tickDirectionIndex=0;
   tickDirectionCount=0;
   lastTickImbalance=0.0;
   lastMultiHorizonScore=0.0;
   lastMultiHorizonAgreement=0.0;
   lastBreakoutDetected=false;
   lastBreakoutStrength=0.0;
   confirmedM1Direction=0;
   confirmedDirectionStartBar=0;
   lastDirectionEvaluationBar=0;
   lastDirectionHoldBars=0;
   lastBullishConfirmCount=0;
   lastBearishConfirmCount=0;
   lastTrendBuyVotes=0;
   lastTrendSellVotes=0;
   lastTrendStrength=0.0;
   lastDirectionSource="TARAMA SECIMI";
   lastSignal=0;
   lastSingleEntryBar=0;
   lastBasketProfit=0.0;
   basketTakeProfitClosing=false;
   continuousFillBusy=false;
}

bool SwitchEngineSymbol(string newSymbol)
{
   if(!IsForexSymbolName(newSymbol))
      return false;

   if(gEngineSymbol==newSymbol && hFastMA!=INVALID_HANDLE &&
      hTrendEMA!=INVALID_HANDLE && hSlowMA!=INVALID_HANDLE &&
      hATR!=INVALID_HANDLE && hRSI!=INVALID_HANDLE &&
      hBands!=INVALID_HANDLE)
      return true;

   // V68 FAST SWITCH:
   // 10K model ortak/global tutulur. Parite degisimi sirasinda diske kaydetme,
   // 10K yeniden initialize, warmup ve 60M history batch YAPILMAZ.
   // Boylece yeni M15 mumunun ilk 10 saniyelik giris penceresi kacirilmaz.
   ReleaseSelectedIndicators();
   gEngineSymbol=newSymbol;
   ResetSelectedSymbolRuntime();

   hFastMA=iMA(EngineSymbol(),InpTF,InpFastMA,0,MODE_EMA,PRICE_CLOSE);
   hTrendEMA=iMA(EngineSymbol(),InpTF,MathMax(2,InpTrendEMAPeriod),0,MODE_EMA,PRICE_CLOSE);
   hSlowMA=iMA(EngineSymbol(),InpTF,InpSlowMA,0,MODE_EMA,PRICE_CLOSE);
   hATR=iATR(EngineSymbol(),InpTF,InpATRPeriod);
   hRSI=iRSI(EngineSymbol(),InpTF,InpRSIPeriod,PRICE_CLOSE);
   hBands=iBands(EngineSymbol(),InpTF,InpBollingerPeriod,0,
                 InpBollingerDeviation,PRICE_CLOSE);

   if(hFastMA==INVALID_HANDLE || hTrendEMA==INVALID_HANDLE ||
      hSlowMA==INVALID_HANDLE || hATR==INVALID_HANDLE ||
      hRSI==INVALID_HANDLE || hBands==INVALID_HANDLE)
   {
      Print("Selected symbol indicator creation failed: ",newSymbol,
            " error: ",GetLastError());
      ReleaseSelectedIndicators();
      return false;
   }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(EngineSymbol());
   trade.SetAsyncMode(false);
   gModelInitialized=true;
   return true;
}

void ApplySelectedCandidate(ForexScanCandidate &candidate)
{
   gFastRefillAfterFlat=false;
   gSelectedScanScore=candidate.score;
   gSelectedScanVolatility=candidate.volatilityPercentile;
   gSelectedScanRSI=candidate.rsi;
   gSelectedScanDirection=candidate.direction;
   gSelectedStreakCount=candidate.streakCandles;
   gSelectedExtremeQuality=candidate.extremeQuality;
   gSelectedExtremeAnchorShift=candidate.streakCandles;
   gSelectedScanReason=candidate.reason;
   confirmedM1Direction=candidate.direction;
   confirmedDirectionStartBar=iTime(EngineSymbol(),InpTF,0);
   lastDirectionEvaluationBar=confirmedDirectionStartBar;
   lastDirectionSource="TUM FOREX TARAMASI: "+candidate.reason;
}

void ProcessMultiSymbolEngine()
{
   // Kar alma ve haftalik kapanis tum bot pozisyonlari icin global calisir.
   if(!ManageWeeklySchedule())
   {
      UpdatePanel();
      return;
   }

   if(!ManageBasketTakeProfit())
   {
      UpdatePanel();
      return;
   }

   if(!DrawdownAllowed())
   {
      UpdatePanel();
      return;
   }

   int target=MathMax(1,InpMaxOpenTrades);

   string openSymbol="";
   bool multipleSymbols=false;
   int allBotPositions=CountAllBotPositions(openSymbol,multipleSymbols);

   // Eski V51'den farkli paritelerde acik pozisyon kaldiysa yeni sepet baslatma.
   if(multipleSymbols)
   {
      lastStatus="ESKI FARKLI PARITE POZISYONLARI VAR - YENI SEPET BEKLIYOR";
      UpdatePanel();
      return;
   }

   // Aktif sepet varken ASLA baska parite secme.
   if(allBotPositions>0)
   {
      // Hedging: pozisyon sayisi sayaci toparlayabilir.
      // Netting: 6 deal tek pozisyonda birlesebilecegi icin emir sayacini DUSURME.
      if(IsHedgingAccount() && gBasketOrdersOpened<allBotPositions)
         gBasketOrdersOpened=allBotPositions;

      if(openSymbol!="" && openSymbol!=EngineSymbol())
      {
         if(!SwitchEngineSymbol(openSymbol))
         {
            lastStatus="AKTIF SEPET PARITESINE GECILEMEDI: "+openSymbol;
            UpdatePanel();
            return;
         }
      }

      if(gBasketSymbol=="")
         gBasketSymbol=openSymbol;
      if(gBasketDirection==0)
         gBasketDirection=BotBasketDirection(openSymbol);

      // Ilk sepet olusurken emirlerden biri reddedilirse, hedefe ulasana kadar
      // sadece AYNI paritede eksik emirleri tekrar dene.
      if(!gBasketEntryComplete)
      {
         if(allBotPositions>=target || gBasketOrdersOpened>=target)
         {
            gBasketEntryComplete=true;
            lastStatus="SEPET TAMAM: "+openSymbol+" | "+
                       IntegerToString(target)+" ISLEM";
         }
         else if(gBasketDirection!=0)
         {
            FillPositionsContinuously(gBasketDirection);
         }
      }
      else
      {
         // V91 SUREKLI REFILL:
         // Hedging hesapta bir pozisyon kapanirsa, ayni EMA42 yonu devam ettigi
         // surece aktif pozisyon sayisini tekrar hedefe tamamla.
         // Ayni anda target'tan FAZLA pozisyon acilmaz.
         if(InpContinuousTrading && IsHedgingAccount() &&
            allBotPositions<target && gBasketDirection!=0)
         {
            int emaDirection=EMA42TrendDirection();
            int candleDirection=CurrentLiveCandleColorDirection(EngineSymbol());

            double refillDistancePoints=0.0;
            bool refillDistanceOk=CandleOpenDistanceReached(EngineSymbol(),
                                                            gBasketDirection,
                                                            refillDistancePoints);

            if(emaDirection==gBasketDirection &&
               candleDirection==gBasketDirection &&
               refillDistanceOk)
            {
               gBasketOrdersOpened=allBotPositions;
               gBasketEntryComplete=false;
               FillPositionsContinuously(gBasketDirection);

               if(CountAllBotTrades()>=target)
                  gBasketEntryComplete=true;
            }
            else
            {
               lastStatus="AKTIF SEPET | EMA42 YONU DEGISTI - YENI EMIR YOK";
            }
         }
         else
         {
            lastStatus="AKTIF SEPET: "+openSymbol+" | KALAN "+
                       IntegerToString(allBotPositions)+"/"+
                       IntegerToString(target)+
                       " | SUREKLI TAKIP";
         }
      }

      UpdatePanel();
      return;
   }

   // Onceki sepet tamamen bitti. Sonraki taramada ayni pariteyi arka arkaya
   // secmemek icin son sepet sembolunu kaydet ve sepet durumunu sifirla.
   if(gBasketSymbol!="")
   {
      gLastOpenedSymbol=gBasketSymbol;
      gBasketSymbol="";
      gBasketDirection=0;
      gBasketEntryComplete=false;
      gBasketOrdersOpened=0;
      gBasketOrderLock=false;
      gBasketPeakProfit=0.0;
      gBasketPeakGiveback=0.0;
      gPeakProfitArmed=false;
      gLastAIProfitEvalMs=0;
      gAIProfitDirectionConfidence=0.50;
      gAIProfitReversal=false;
      gNeedSymbolScan=true;
      if(InpContinuousTrading)
      {
         gFastRefillAfterFlat=true;
         gLastUniverseScanMs=0; // sepet biter bitmez tekrar taramaya izin ver
      }
   }

   ulong nowMs=GetTickCount64();
   if(nowMs-gLastUniverseScanMs<250)
   {
      UpdatePanel();
      return;
   }
   gLastUniverseScanMs=nowMs;

   // Bosken tum Forex evreninden TEK en mantikli pariteyi sec.
   ForexScanCandidate best;
   if(!SelectBestForexCandidate(best))
   {
      lastStatus="EMA42 EGIM + ACIK PIYASA + DUSUK SPREAD UYGUN PARITE BEKLENIYOR";
      UpdatePanel();
      return;
   }

   if(!SwitchEngineSymbol(best.symbol))
   {
      lastStatus="SECILEN PARITE HAZIRLANAMADI: "+best.symbol;
      UpdatePanel();
      return;
   }

   ApplySelectedCandidate(best);
   gBasketSymbol=best.symbol;
   gBasketDirection=best.direction;
   gBasketEntryComplete=false;
   gBasketOrdersOpened=0;
   gBasketOrderLock=false;
   gBasketPeakProfit=0.0;
   gBasketPeakGiveback=0.0;
   gPeakProfitArmed=false;
   gLastAIProfitEvalMs=0;
   gAIProfitDirectionConfidence=0.50;
   gAIProfitReversal=false;
   gNeedSymbolScan=false;
   gSelectionTimeMs=nowMs;

   // V68 FAST ENTRY:
   // Aday ilk 10 saniye icinde secildi. Agir 10K inference yerine emri hemen
   // gonder; ExecuteTrade kapali piyasa, trade mode, taze tick ve breakout'u
   // tekrar kontrol eder. AI/60M hafiza arka planda calismaya devam eder.
   int verifyAge=-1;
   LiveCandleColorFirstSeconds(EngineSymbol(),verifyAge);
   int verifyDirection=EMA42TrendDirection();
   int verifyCandleDirection=CurrentLiveCandleColorDirection(EngineSymbol());

   bool entryWindowOk=(verifyAge>=0 &&
                       (InpContinuousEntryAnyTime ||
                        verifyAge<=MathMax(1,InpEntryFirstSeconds)));

   double verifyDistancePoints=0.0;
   bool distanceOk=CandleOpenDistanceReached(EngineSymbol(),
                                             best.direction,
                                             verifyDistancePoints);

   if(entryWindowOk &&
      verifyDirection==best.direction &&
      verifyCandleDirection==best.direction &&
      verifyDirection!=0 &&
      distanceOk)
   {
      lastLiveEntryAgeSeconds=verifyAge;
      FillPositionsContinuously(best.direction);
   }
   else
   {
      if(!entryWindowOk)
         lastStatus="M15 ILK "+IntegerToString(InpEntryFirstSeconds)+
                    " SN GECTI - YENI MUM BEKLENIYOR";
      else
         lastStatus="EMA42 EGIM DEGISIYOR/YATAY - YENI SINYAL BEKLENIYOR";
   }

   if(gBasketOrdersOpened>=target)
      gBasketEntryComplete=true;

   UpdatePanel();
}

void UpdatePanel()
{
   Comment("TUM FOREX V91 - EMA42 + M15 + ULTRA MAX KAR | 8 GIRDI",
           "\nTaranan Forex sembolu: ",ArraySize(gForexSymbols),
           " | Secilen parite: ",EngineSymbol(),
           "\nOncelik: EN DUSUK SPREAD -> EMA42+MUM -> HIZLI PIYASA -> 10K AI",
           "\nTarama skoru: ",DoubleToString(gSelectedScanScore,2),
           " | Secim: ",gSelectedScanReason,
           "\nSinyal: ",(confirmedM1Direction>0?"BUY":
                          confirmedM1Direction<0?"SELL":"BEKLE"),
           " | Analiz mumu: ",gSelectedStreakCount,
           "\nBUY: EMA42 YUKARI + YESIL MUM | SELL: EMA42 ASAGI + KIRMIZI MUM",
           "\nGiris mesafesi: M15 mum acilisindan ",DoubleToString(InpEntryDistancePoints,1)," point",
           "\nGiris modu: ",(InpContinuousEntryAnyTime?"SUREKLI - M15 HER AN":"ILK PENCERE")," | Ilk pencere: ",InpEntryFirstSeconds," sn | Gecen: ",lastLiveEntryAgeSeconds," sn",
           "\nArd arda mum / ek point: YOK",
           " | Kalite: ",DoubleToString(gSelectedExtremeQuality*100.0,1),"%",
           "\nVolatilite yuzdelik/oran: ",
                    DoubleToString(lastVolatilityPercentile,1),"% / ",
                    DoubleToString(lastVolatilityRatio,2),
           " | Orta-ust bolge: ",DoubleToString(InpMediumVolMinPercentile,0),"-",
                              DoubleToString(InpMediumVolMaxPercentile,0),"%",
           "\nSpread anlik/minimum: ",lastCurrentSpread,"/",lastMinimumSpread,
           " | Minimum spread: ",(InpLowestSpreadEntry?"ACIK":"KAPALI"),
           "\n10K HIERARCHICAL AI olasilik/guven: ",DoubleToString(lastAIProbability*100.0,1),"% / ",
                    DoubleToString(lastAIConfidence*100.0,1),"%",
           " | Ufuk: ",AI_MULTI_HORIZONS,
           "\nZamansal/Hiyerarsik prior: ",DoubleToString(lastAITemporalPrior*100.0,1),"% / ",
                    DoubleToString(lastAIHierarchicalPrior*100.0,1),"%",
           " | Uzman uzlasma: ",DoubleToString(lastAISpecialistConsensus*100.0,1),"%",
           "\nRejim uzlasma/drift: ",DoubleToString(lastAIRegimeConsensus*100.0,1),"% / ",
                    DoubleToString(lastAIDriftScore*100.0,1),"%",
           " | Belirsizlik: ",DoubleToString(lastAIUncertainty*100.0,1),"%",
           " | Derin/Mikro guven: ",DoubleToString(lastAIDeepReliability*100.0,1),"%/",
                    DoubleToString(lastAIMicroReliability*100.0,1),"%",
           "\nAI birlesim/soft hedef: ",DoubleToString(lastAIFusionQuality*100.0,1),"% / ",
                    DoubleToString(lastAISoftTarget*100.0,1),"%",
           " | Egitim: ",aiTrainingCount,
           "\nGecmis ogrenme: ",aiHistoryProcessed,"/",aiHistoryTarget,
           " | Epoch: ",aiHistoryEpoch,
           " | Benzersiz mevcut: ",aiHistoryUniqueAvailable,
           "\nGecmis hiz hedef/gercek: ",AI_Gecmis_Hedef_Hiz," / ",
                    DoubleToString(aiHistoryThroughput,0)," mum/sn",
           " | 10K tarih backprop: ",aiHistoryDeepSamples,
           "\nKalici hafiza: ",(AI_Kalici_Hafiza?"ACIK":"KAPALI"),
           " | Tekrarli epoch: ",(AI_Gecmis_Tekrarli_Ogrenme?"ACIK":"KAPALI"),
           "\n10K mikro oy BUY/SELL/NOTR: ",lastMicroBuyVotes,"/",lastMicroSellVotes,"/",lastMicroNeutralVotes,
           "\nSepet paritesi: ",(gBasketSymbol==""?"YOK":gBasketSymbol),
           " | Yon: ",(gBasketDirection>0?"BUY":gBasketDirection<0?"SELL":"BEKLE"),
           "\nPozisyon: ",CountAllBotTrades(),"/",MathMax(1,InpMaxOpenTrades),
           " | Bu sepette acilan toplam: ",gBasketOrdersOpened,
           " | Sepet tamam: ",(gBasketEntryComplete?"EVET":"HAYIR"),
           "\nZirve kar baslangici: ",DoubleToString(Kari_Al_Para,2),
           " | Peak: ",DoubleToString(gBasketPeakProfit,2),
           " | Geri cekilme: ",DoubleToString(gBasketPeakGiveback,2),
           " | Adaptif tol %: ",DoubleToString(gDynamicPeakGivebackPct,1),
           "\nKar hizi: ",DoubleToString(gProfitVelocityEma,4),
           " | MAX KAR modu: ",(InpAdaptiveMaxProfit?"ACIK":"KAPALI"),
           "\nAI max-kar guveni: ",DoubleToString(gAIProfitDirectionConfidence*100.0,1),"%",
           " | AI donus: ",(gAIProfitReversal?"EVET":"HAYIR"),
           " | EMA42/Mum zirve cikisi: ",(InpExitOnEMA42CandleReversal?"ACIK":"KAPALI"),
           "\nKari Al (para): ",DoubleToString(Kari_Al_Para,2),
           " | Ultra zirve kilidi: ",(InpUltraPeakLock?"ACIK":"KAPALI"),
           " | Zirve geri cekilme: ",DoubleToString(InpUltraPeakRetreatPct,2),"%",
           " | Para: ",DoubleToString(InpUltraPeakRetreatMoney,3),
           " | Surekli islem: ",(InpContinuousTrading?"ACIK":"KAPALI")," | Surekli giris: ",(InpContinuousEntryAnyTime?"ACIK":"KAPALI"),
           " | Peak kilit: ",(InpFastPeakProfitLock?"ACIK":"KAPALI"),
           "\nHaftalik saat (broker): Pzt ",
                    IntegerToString(InpMondayOpenHour),":",
                    (InpMondayOpenMinute<10?"0":""),
                    IntegerToString(InpMondayOpenMinute),
                    " / Cum ",
                    IntegerToString(InpFridayCloseHour),":",
                    (InpFridayCloseMinute<10?"0":""),
                    IntegerToString(InpFridayCloseMinute),
           "\nSecim onceligi: EN DUSUK SPREAD -> EMA42+MUM UYUM -> HIZLI PIYASA -> AI",
           "\nHaric tutulan yavas parite: ZARJPY",
           "\nOrta-ust volatilite onceligi: ",(InpMediumVolatilityPriority?"ACIK":"KAPALI"),
                    " | Yedek secim: ",(InpAllowVolatilityFallback?"ACIK":"KAPALI"),
           "\nEMA42 filtresi: ",(InpUseEMA42TrendFilter?"ACIK":"KAPALI"),
                    " | EMA periyot: ",InpTrendEMAPeriod,
                    " | EMA yon: ",(EMA42TrendDirection()>0?"BUY":
                                   (EMA42TrendDirection()<0?"SELL":"NOTR")),
           "\nKapali piyasa korumasi: ",(InpStrictClosedMarketGuard?"KATI":"NORMAL"),
                    " | Max tick yasi: ",InpMaxTickAgeSeconds," sn",
                    " | Seans bilgisi zorunlu: ",(InpRequireBrokerSession?"EVET":"HAYIR"),
           "\nDurum: ",lastStatus);
}

void ProcessEngine()
{
   if(!IsForexSymbol())
   {
      lastStatus="BU EA SADECE FOREX PARITELERI ICINDIR";
      UpdatePanel();
      return;
   }

   if(!UpdateSpreadSnapshot())
   {
      UpdatePanel();
      return;
   }

   if(!ManageWeeklySchedule())
   {
      UpdatePanel();
      return;
   }

   if(!ManageBasketTakeProfit())
   {
      UpdatePanel();
      return;
   }

   long minimumHistory=MinimumHistoryForTrading();
   if(AI_Gecmis_Hazirlik_Bekle &&
      aiHistoryProcessed<minimumHistory)
   {
      lastStatus="SON MUM HAFIZASI HAZIRLANIYOR: "+
                 IntegerToString((int)aiHistoryProcessed)+"/"+
                 IntegerToString((int)minimumHistory);
      UpdatePanel();
      return;
   }

   if(!DrawdownAllowed())
   {
      UpdatePanel();
      return;
   }

   int signal=EvaluateStrategy();
   lastSignal=signal;

   if(signal!=0)
      FillPositionsContinuously(signal);

   UpdatePanel();
}

int OnInit()
{
   if(!IsForexSymbol())
   {
      Print("FOREX V91 bir Forex grafigine eklenmelidir: ",EngineSymbol());
      return INIT_FAILED;
   }

   hFastMA=iMA(EngineSymbol(),InpTF,InpFastMA,0,MODE_EMA,PRICE_CLOSE);
   hTrendEMA=iMA(EngineSymbol(),InpTF,MathMax(2,InpTrendEMAPeriod),0,MODE_EMA,PRICE_CLOSE);
   hSlowMA=iMA(EngineSymbol(),InpTF,InpSlowMA,0,MODE_EMA,PRICE_CLOSE);
   hATR=iATR(EngineSymbol(),InpTF,InpATRPeriod);
   hRSI=iRSI(EngineSymbol(),InpTF,InpRSIPeriod,PRICE_CLOSE);
   hBands=iBands(EngineSymbol(),InpTF,InpBollingerPeriod,0,
                 InpBollingerDeviation,PRICE_CLOSE);

   if(hFastMA==INVALID_HANDLE ||
      hTrendEMA==INVALID_HANDLE ||
      hSlowMA==INVALID_HANDLE ||
      hATR==INVALID_HANDLE ||
      hRSI==INVALID_HANDLE ||
      hBands==INVALID_HANDLE)
   {
      Print("Indicator handles could not be created. Error: ",GetLastError());
      return INIT_FAILED;
   }

   ArrayResize(strategyVotes,STRATEGY_COUNT);
   ArrayInitialize(strategyVotes,0.0);
   ArrayResize(directStrategyVotes,DIRECT_STRATEGY_COUNT);
   ArrayInitialize(directStrategyVotes,0.0);
   ArrayResize(advancedStrategyVotes,ADVANCED_STRATEGY_COUNT);
   ArrayInitialize(advancedStrategyVotes,0.0);
   InitializeDeepAI();
   bool loadedNeuralState=LoadNeuralState();
   InitializeHistoryMemory();
   if(!loadedNeuralState)
   {
      WarmupDeepAI();
      SaveNeuralState(true);
   }
   ProcessHistoryMemoryBatch();

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(EngineSymbol());
   trade.SetAsyncMode(false);
   gModelInitialized=true;

   int universeCount=BuildForexUniverse();
   if(universeCount<=0)
   {
      Print("No tradable Forex symbols were found on the broker server.");
      return INIT_FAILED;
   }

   gNeedSymbolScan=true;
   gLastUniverseScanMs=0;

   EventSetMillisecondTimer(50);
   ProcessMultiSymbolEngine();

   Print("ALL FOREX V91 12-candle direction + 10K HIERARCHICAL AI + 384 horizons + 60M repeated persistent memory + 800K/s target + breakout guard strict-basket initialized. Universe: ",universeCount,
         " Seven inputs. Deep state loaded: ",loadedNeuralState,
         " Recent history min/target: ",
         AI_Gecmis_Min_Mum,"/",AI_Gecmis_Hedef_Mum,
         " Lowest spread entry: ",InpLowestSpreadEntry,
         " RSI: ",InpRSIPeriod,
         " Bollinger: ",InpBollingerPeriod,"/",InpBollingerDeviation,
         " Continuous refill: ",InpContinuousOpen,
         " Direct strategies: ",DIRECT_STRATEGY_COUNT,
         " Advanced strategies: ",ADVANCED_STRATEGY_COUNT,
         " Parameter strategies: ",STRATEGY_COUNT,
         " Neural networks: ",ActiveMicroNetworkCount()+AI_MODELS,
         " AI training samples: ",aiTrainingCount,
         " History processed/target: ",aiHistoryProcessed,"/",aiHistoryTarget,
         " Timeframe: ",EnumToString(InpTF));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   SaveNeuralState(true);
   SaveHistoryMemory(true);

   if(hFastMA!=INVALID_HANDLE) IndicatorRelease(hFastMA);
   if(hSlowMA!=INVALID_HANDLE) IndicatorRelease(hSlowMA);
   if(hATR!=INVALID_HANDLE) IndicatorRelease(hATR);
   if(hRSI!=INVALID_HANDLE) IndicatorRelease(hRSI);
   if(hBands!=INVALID_HANDLE) IndicatorRelease(hBands);

   Comment("");
}

void OnTick()
{
   ProcessMultiSymbolEngine();
}

void OnTradeTransaction(const MqlTradeTransaction &transaction,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(!InpContinuousOpen)
      return;

   ProcessMultiSymbolEngine();
}

void OnTimer()
{
   // Canli emir ve zirve-kar yonetimi her zaman ilk onceliktir.
   ProcessMultiSymbolEngine();

   // 60M tekrarli egitim agir olabilir. Acik pozisyon varken veya yeni M15
   // mumunun ilk giris saniyelerinde egitimi duraklat; emir/kar takibi gecikmesin.
   if(CountAllBotTrades()>0)
      return;

   int age=-1;
   LiveCandleColorFirstSeconds(EngineSymbol(),age);

   // Surekli giris modunda emir motoru her timer turunda once calisir.
   // Agir tarih egitimi, klasik ilk-N-saniye modu kullaniliyorsa o pencereyi geciktirmez.
   if(!InpContinuousEntryAnyTime &&
      age>=0 && age<=MathMax(1,InpEntryFirstSeconds))
      return;

   ProcessHistoryMemoryBatch();
}
