//+------------------------------------------------------------------+
//|                        SmartScalper Pro AI v3.0                  |
//|                   İŞLEM AÇACAK - GÜVENILIR VERSİYON              |
//|                      Copyright 2026, AI Trading                  |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026 AI Trading"
#property link      "https://github.com/blacktech589-cyber"
#property version   "3.0"
#property strict

#include <Trade\Trade.mqh>
CTrade trade;

//========== EXPERT AYARLARI ==========
input group "🤖 DERİN ÖĞRENME AYARLARI"
input int      InpHistoryBars      = 1000;      // Geçmiş analiz (1000 mum)
input int      InpSequenceLength   = 60;        // LSTM hafıza derinliği
input int      InpFeatureCount     = 25;        // Özellik sayısı
input double   InpConfidence       = 0.55;      // DÜŞÜK Güven eşiği (işlem açsın!)
input double   InpMinSignalStrength= 1.0;       // 1+ gösterge yeterli

input group "💰 RİSK YÖNETİMİ"
input double   InpLotSize          = 0.01;      // Lot miktarı (KÜÇÜK test)
input double   InpRiskPercent      = 2.0;       // Hesap riskinin %
input double   InpTakeProfitPct    = 1.5;       // Kâr hedefi %
input double   InpStopLossPct      = 0.7;       // Zarar durdurma %
input int      InpMaxSpread        = 50;        // Maksimum spread (puan)
input int      InpMaxTrades        = 2;         // Maksimum pozisyon (2'ye çıkardı)
input ulong    InpMagicNumber      = 778899;    // Sihirli numara

input group "📊 TİCARET SAATLERİ"
input bool     InpAlwaysTrade      = true;      // HER SAATİ TİCART YAPMA!
input int      InpStartHour        = 0;         // Başlangıç (0 = açık)
input int      InpEndHour          = 23;        // Bitiş (23 = açık)

//========== GÖSTERGELER ==========
int rsi_handle, atr_handle;
int ema_fast, ema_mid, ema_slow;
int macd_handle, bb_handle;
int volume_handle;

MqlRates candles[];
double global_trend_bias = 0.0;
double longterm_highest = 0.0;
double longterm_lowest = 0.0;

int last_trade_bar = -1;  // Aynı mumda iki kez işlem açmamak için

struct TradeStats {
    int total_trades;
    int wins;
    int losses;
    double total_profit;
};
TradeStats stats = {0, 0, 0, 0.0};

//+------------------------------------------------------------------+
//| Başlatma Fonksiyonu                                              |
//+------------------------------------------------------------------+
int OnInit()
{
    Print("🚀 SmartScalper Pro AI v3.0 BAŞLATILIYOR!");
    
    trade.SetExpertMagicNumber(InpMagicNumber);
    trade.SetDeviationInPoints(100);
    trade.SetTypeFilling(ORDER_FILLING_IOC);
    
    // Tarihsel analiz
    MqlRates hist_rates[];
    ArraySetAsSeries(hist_rates, true);
    
    int bars = CopyRates(_Symbol, PERIOD_H1, 0, InpHistoryBars, hist_rates);
    if(bars > 0)
    {
        double sum_close = 0;
        longterm_highest = hist_rates[0].high;
        longterm_lowest = hist_rates[0].low;
        
        for(int i = 0; i < bars; i++)
        {
            sum_close += hist_rates[i].close;
            if(hist_rates[i].high > longterm_highest) longterm_highest = hist_rates[i].high;
            if(hist_rates[i].low < longterm_lowest) longterm_lowest = hist_rates[i].low;
        }
        
        double avg_price = sum_close / (double)bars;
        double current = hist_rates[0].close;
        global_trend_bias = (current - avg_price) / (longterm_highest - longterm_lowest + 0.00001);
        
        Print("✅ ", bars, " mum analiz ediliyor... Trend Skoru: ", DoubleToString(global_trend_bias, 3));
    }
    
    // Göstergeler
    rsi_handle   = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE);
    atr_handle   = iATR(_Symbol, PERIOD_H1, 14);
    ema_fast     = iMA(_Symbol, PERIOD_H1, 9, 0, MODE_EMA, PRICE_CLOSE);
    ema_mid      = iMA(_Symbol, PERIOD_H1, 21, 0, MODE_EMA, PRICE_CLOSE);
    ema_slow     = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
    macd_handle  = iMACD(_Symbol, PERIOD_H1, 12, 26, 9, PRICE_CLOSE);
    bb_handle    = iBands(_Symbol, PERIOD_H1, 20, 2, PRICE_CLOSE);
    
    if(rsi_handle == INVALID_HANDLE || atr_handle == INVALID_HANDLE ||
       ema_fast == INVALID_HANDLE || ema_mid == INVALID_HANDLE || ema_slow == INVALID_HANDLE)
    {
        Print("❌ Gösterge hataları!");
        return(INIT_FAILED);
    }
    
    ArrayResize(candles, InpSequenceLength + 10);
    
    Print("✅ İNİT BAŞARILI - HAZIR");
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Durma Fonksiyonu                                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    IndicatorRelease(rsi_handle);
    IndicatorRelease(atr_handle);
    IndicatorRelease(ema_fast);
    IndicatorRelease(ema_mid);
    IndicatorRelease(ema_slow);
    IndicatorRelease(macd_handle);
    IndicatorRelease(bb_handle);
    
    Print("📊 TICARET İSTATİSTİKLERİ:");
    Print("   Toplam İşlem: ", stats.total_trades);
    Print("   Kazananlar: ", stats.wins);
    Print("   Kaybedenler: ", stats.losses);
    Print("   Net Kâr: $", DoubleToString(stats.total_profit, 2));
}

//+------------------------------------------------------------------+
//| MAIN TİCARET FONKSİYONU                                          |
//+------------------------------------------------------------------+
void OnTick()
{
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    
    if(ask <= 0 || bid <= 0)
    {
        Print("⚠️ Fiyat hatası");
        return;
    }
    
    // Ticaret saati kontrolü
    if(!InpAlwaysTrade && !IsTradeTime())
    {
        return;
    }
    
    // Spread kontrolü
    long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
    if(spread > InpMaxSpread)
    {
        return;
    }
    
    // VOLATİLİTE KONTROLÜ
    double atr_vals[];
    ArraySetAsSeries(atr_vals, true);
    if(CopyBuffer(atr_handle, 0, 0, 1, atr_vals) <= 0)
        return;
    
    if(atr_vals[0] > 200.0)  // Çok yüksek volatilite
    {
        return;
    }
    
    // MUM VERİSİ GÜNCELLE
    if(!UpdateCandleData())
        return;
    
    // TEKNIK GÖSTERGELER ÇALIŞTIRILDI
    double buy_prob = 0.5;
    double sell_prob = 0.5;
    int signal_strength = AnalyzeTechnicals(buy_prob, sell_prob);
    
    Print("📊 Buy: ", DoubleToString(buy_prob * 100, 1), "% | Sell: ", 
          DoubleToString(sell_prob * 100, 1), "% | Güç: ", signal_strength, 
          " | Açık: ", CountOpenPositions(), "/", InpMaxTrades);
    
    // SİNYAL OLUŞTUR
    bool buy_signal = (buy_prob >= InpConfidence);
    bool sell_signal = (sell_prob >= InpConfidence);
    
    // AÇIK POZİSYONLARI KONTROL ET
    CheckOpenPositions(ask, bid);
    
    // TİCARET AÇMA
    int open_pos = CountOpenPositions();
    
    if(open_pos < InpMaxTrades && last_trade_bar != iBarShift(_Symbol, PERIOD_H1, TimeCurrent()))
    {
        if(buy_signal && buy_prob > sell_prob)
        {
            OpenBuyTrade(ask);
            last_trade_bar = iBarShift(_Symbol, PERIOD_H1, TimeCurrent());
        }
        else if(sell_signal && sell_prob > buy_prob)
        {
            OpenSellTrade(bid);
            last_trade_bar = iBarShift(_Symbol, PERIOD_H1, TimeCurrent());
        }
    }
}

//+------------------------------------------------------------------+
//| ALIM İŞLEMİ AÇMA                                                 |
//+------------------------------------------------------------------+
void OpenBuyTrade(double ask)
{
    double sl = ask * (1.0 - InpStopLossPct / 100.0);
    double tp = ask * (1.0 + InpTakeProfitPct / 100.0);
    
    if(trade.Buy(InpLotSize, _Symbol, ask, sl, tp, "🚀 AI BUY"))
    {
        stats.total_trades++;
        Print("✅ ALIM: ", InpLotSize, " @ ", DoubleToString(ask, 5), 
              " SL:", DoubleToString(sl, 5), " TP:", DoubleToString(tp, 5));
    }
    else
    {
        Print("❌ ALIM HATASI: ", GetLastError());
    }
}

//+------------------------------------------------------------------+
//| SATIM İŞLEMİ AÇMA                                                |
//+------------------------------------------------------------------+
void OpenSellTrade(double bid)
{
    double sl = bid * (1.0 + InpStopLossPct / 100.0);
    double tp = bid * (1.0 - InpTakeProfitPct / 100.0);
    
    if(trade.Sell(InpLotSize, _Symbol, bid, sl, tp, "🔽 AI SELL"))
    {
        stats.total_trades++;
        Print("✅ SATIM: ", InpLotSize, " @ ", DoubleToString(bid, 5), 
              " SL:", DoubleToString(sl, 5), " TP:", DoubleToString(tp, 5));
    }
    else
    {
        Print("❌ SATIM HATASI: ", GetLastError());
    }
}

//+------------------------------------------------------------------+
//| AÇIK POZİSYON KONTROLÜ                                           |
//+------------------------------------------------------------------+
void CheckOpenPositions(double ask, double bid)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(PositionGetSymbol(i) != _Symbol || 
           PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
            continue;
        
        ulong ticket = PositionGetTicket(i);
        long pos_type = PositionGetInteger(POSITION_TYPE);
        double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
        
        // Kar/Zarar hesapla
        double current_price = (pos_type == POSITION_TYPE_BUY) ? bid : ask;
        double profit_pct = ((current_price - open_price) / open_price) * 100.0;
        
        // İstatistik
        if(profit_pct > 0) stats.wins++;
        else stats.losses++;
        stats.total_profit += profit_pct;
    }
}

//+------------------------------------------------------------------+
//| TEKNIK ANDİKATÖRLER ANALİZİ (TEK FONKSİYON)                      |
//+------------------------------------------------------------------+
int AnalyzeTechnicals(double &buy_prob, double &sell_prob)
{
    int strength = 0;
    
    double fast[], mid[], slow[], rsi_vals[];
    double macd_main[], macd_signal[];
    double bb_upper[], bb_lower[];
    
    ArraySetAsSeries(fast, true);
    ArraySetAsSeries(mid, true);
    ArraySetAsSeries(slow, true);
    ArraySetAsSeries(rsi_vals, true);
    ArraySetAsSeries(macd_main, true);
    ArraySetAsSeries(macd_signal, true);
    ArraySetAsSeries(bb_upper, true);
    ArraySetAsSeries(bb_lower, true);
    
    // Göstergeleri oku
    CopyBuffer(ema_fast, 0, 0, 2, fast);
    CopyBuffer(ema_mid, 0, 0, 2, mid);
    CopyBuffer(ema_slow, 0, 0, 2, slow);
    CopyBuffer(rsi_handle, 0, 0, 2, rsi_vals);
    CopyBuffer(macd_handle, 0, 0, 2, macd_main);
    CopyBuffer(macd_handle, 1, 0, 2, macd_signal);
    CopyBuffer(bb_handle, 1, 0, 2, bb_upper);
    CopyBuffer(bb_handle, 2, 0, 2, bb_lower);
    
    // 1. EMA CROSSOVER
    if(fast[0] > mid[0] && mid[0] > slow[0])
    {
        buy_prob = 0.75;
        sell_prob = 0.25;
        strength += 2;
        Print("   ✓ EMA BULLISH");
    }
    else if(fast[0] < mid[0] && mid[0] < slow[0])
    {
        buy_prob = 0.25;
        sell_prob = 0.75;
        strength += 2;
        Print("   ✓ EMA BEARISH");
    }
    
    // 2. RSI ANALIZI
    if(rsi_vals[0] > 50 && rsi_vals[0] < 75)
    {
        buy_prob *= 1.2;
        strength += 1;
        Print("   ✓ RSI BULLISH");
    }
    else if(rsi_vals[0] < 50 && rsi_vals[0] > 25)
    {
        sell_prob *= 1.2;
        strength += 1;
        Print("   ✓ RSI BEARISH");
    }
    
    // 3. MACD ANALIZI
    if(macd_main[0] > macd_signal[0])
    {
        buy_prob *= 1.15;
        strength += 1;
        Print("   ✓ MACD BULLISH");
    }
    else if(macd_main[0] < macd_signal[0])
    {
        sell_prob *= 1.15;
        strength += 1;
        Print("   ✓ MACD BEARISH");
    }
    
    // 4. BOLLINGER BANDS
    if(candles[0].close < bb_lower[0])
    {
        buy_prob *= 1.15;
        strength += 1;
        Print("   ✓ BANDS OVERBOUND");
    }
    
    // Normalize
    double total = buy_prob + sell_prob;
    if(total > 0)
    {
        buy_prob /= total;
        sell_prob /= total;
    }
    
    return strength;
}

//+------------------------------------------------------------------+
//| MUM VERİSİ GÜNCELLE                                              |
//+------------------------------------------------------------------+
bool UpdateCandleData()
{
    MqlRates temp_rates[];
    ArraySetAsSeries(temp_rates, true);
    
    if(CopyRates(_Symbol, PERIOD_H1, 0, InpSequenceLength + 5, temp_rates) < InpSequenceLength)
        return false;
    
    ArrayResize(candles, InpSequenceLength);
    ArrayCopy(candles, temp_rates, 0, 0, InpSequenceLength);
    
    return true;
}

//+------------------------------------------------------------------+
//| AÇIK POZİSYON SAYISI                                             |
//+------------------------------------------------------------------+
int CountOpenPositions()
{
    int count = 0;
    
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(PositionGetSymbol(i) == _Symbol && 
           PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
            count++;
    }
    
    return count;
}

//+------------------------------------------------------------------+
//| TİCARET SAATİ KONTROLÜ                                           |
//+------------------------------------------------------------------+
bool IsTradeTime()
{
    int hour = Hour();
    return (hour >= InpStartHour && hour < InpEndHour);
}
