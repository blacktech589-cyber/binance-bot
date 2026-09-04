//+------------------------------------------------------------------+
//|                        SmartScalper Pro AI v2.0                  |
//|                   Derin Öğrenme Tabanlı Ticaret Robotu           |
//|                      Copyright 2026, AI Trading                  |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026 AI Trading"
#property link      "https://github.com/blacktech589-cyber"
#property version   "2.0"
#property strict

#include <Trade\Trade.mqh>
CTrade trade;

//========== EXPERT AYARLARI ==========
input group "🤖 DERİN ÖĞRENME AYARLARI"
input int      InpHistoryBars      = 1000;      // Geçmiş analiz (1000 mum)
input int      InpSequenceLength   = 60;        // LSTM hafıza derinliği
input int      InpFeatureCount     = 25;        // Özellik sayısı
input double   InpConfidence       = 0.72;      // Güven eşiği (daha akıllı)
input double   InpMinSignalStrength= 2.0;       // Minimum sinyal gücü

input group "💰 RİSK YÖNETİMİ"
input double   InpLotSize          = 0.01;      // Lot miktarı
input double   InpRiskPercent      = 2.0;       // Hesap riskinin %
input double   InpTakeProfitPct    = 1.8;       // Kâr hedefi %
input double   InpStopLossPct      = 0.9;       // Zarar durdurma %
input int      InpMaxSpread        = 40;        // Maksimum spread (puan)
input int      InpMaxTrades        = 1;         // Maksimum pozisyon
input ulong    InpMagicNumber      = 778899;    // Sihirli numara

input group "📊 TİCARET SAATLERİ"
input int      InpStartHour        = 8;         // Başlangıç saati
input int      InpEndHour          = 22;        // Bitiş saati
input bool     InpUseNewYorkSession= true;      // NY seansını kullan

//========== GÖSTERGELER ==========
int rsi_handle, atr_handle;
int ema_fast, ema_mid, ema_slow;
int macd_handle, bb_handle;
int volume_handle;

MqlRates candles[];
double global_trend_bias = 0.0;
double longterm_highest = 0.0;
double longterm_lowest = 0.0;

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
    trade.SetExpertMagicNumber(InpMagicNumber);
    trade.SetDeviationInPoints(50);
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
    
    // ONNX Derin Öğrenme Modeli
    long onnx_handle = OnnxCreate("smart_model.onnx", ONNX_DEFAULT);
    if(onnx_handle != INVALID_HANDLE)
    {
        Print("🧠 ONNX Model Yüklendi!");
        long input_shape[] = {1, InpSequenceLength, InpFeatureCount};
        long output_shape[] = {1, 2};
        OnnxSetInputShape(onnx_handle, 0, input_shape);
        OnnxSetOutputShape(onnx_handle, 0, output_shape);
    }
    else
    {
        Print("⚠️ ONNX Model Bulunamadı - Fallback Mode");
    }
    
    // Göstergeler
    rsi_handle   = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE);
    atr_handle   = iATR(_Symbol, PERIOD_H1, 14);
    ema_fast     = iMA(_Symbol, PERIOD_H1, 9, 0, MODE_EMA, PRICE_CLOSE);
    ema_mid      = iMA(_Symbol, PERIOD_H1, 21, 0, MODE_EMA, PRICE_CLOSE);
    ema_slow     = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
    macd_handle  = iMACD(_Symbol, PERIOD_H1, 12, 26, 9, PRICE_CLOSE);
    bb_handle    = iBands(_Symbol, PERIOD_H1, 20, 2, PRICE_CLOSE);
    volume_handle= iVolumes(_Symbol, PERIOD_H1, VOLUME_TICK);
    
    if(rsi_handle == INVALID_HANDLE || atr_handle == INVALID_HANDLE)
        return(INIT_FAILED);
    
    ArrayResize(candles, InpSequenceLength + 10);
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
    IndicatorRelease(volume_handle);
    
    Print("📊 Ticaret İstatistikleri:");
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
    
    // Pazar saati kontrolü
    if(!IsTradeTime())
        return;
    
    // 1️⃣ AÇIK POZİSYON KONTROLÜ (Kar/Zarar)
    CheckOpenPositions(ask, bid);
    
    // 2️⃣ SPREAD KONTROLÜ (Maksimum 40 puan)
    long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
    if(spread > InpMaxSpread)
    {
        Print("⚠️ Spread çok yüksek: ", spread, " puan");
        return;
    }
    
    // 3️⃣ VOLATİLİTE KONTROLÜ (ATR)
    double atr_vals[];
    ArraySetAsSeries(atr_vals, true);
    CopyBuffer(atr_handle, 0, 0, 1, atr_vals);
    
    if(atr_vals[0] > 100.0)
    {
        Print("⚠️ Volatilite çok yüksek: ", DoubleToString(atr_vals[0], 2));
        return;
    }
    
    // 4️⃣ MUM VERİSİ GÜNCELLE
    if(!UpdateCandleData())
        return;
    
    // 5️⃣ ÖZELLİKLER HAZIRLA
    float feature_matrix[];
    if(!PrepareSmartFeatures(feature_matrix))
        return;
    
    // 6️⃣ AI TAHMİNİ (ONNX veya Fallback)
    double buy_prob = 0.5, sell_prob = 0.5;
    GetAIPrediction(feature_matrix, buy_prob, sell_prob);
    
    // 7️⃣ TEKNIK ANDİKATÖRLER ANALİZİ
    int signal_strength = AnalyzeTechnicals(buy_prob, sell_prob);
    
    // 8️⃣ SİNYAL OLUŞTUR
    bool buy_signal = (buy_prob >= InpConfidence && signal_strength >= (int)InpMinSignalStrength);
    bool sell_signal = (sell_prob >= InpConfidence && signal_strength >= (int)InpMinSignalStrength);
    
    Print("📊 Buy: ", DoubleToString(buy_prob * 100, 1), "% | Sell: ", 
          DoubleToString(sell_prob * 100, 1), "% | Sinyal: ", signal_strength);
    
    // 9️⃣ TİCARET AÇMA
    int open_pos = CountOpenPositions();
    
    if(open_pos < InpMaxTrades)
    {
        if(buy_signal)
        {
            double sl = ask - (ask * InpStopLossPct / 100.0);
            double tp = ask + (ask * InpTakeProfitPct / 100.0);
            
            if(trade.Buy(InpLotSize, _Symbol, ask, sl, tp, "🚀 AI BUY"))
            {
                stats.total_trades++;
                Print("✅ ALIM İŞLEMİ: ", InpLotSize, " Lot @ ", DoubleToString(ask, 5));
            }
        }
        else if(sell_signal)
        {
            double sl = bid + (bid * InpStopLossPct / 100.0);
            double tp = bid - (bid * InpTakeProfitPct / 100.0);
            
            if(trade.Sell(InpLotSize, _Symbol, bid, sl, tp, "🔽 AI SELL"))
            {
                stats.total_trades++;
                Print("✅ SATIM İŞLEMİ: ", InpLotSize, " Lot @ ", DoubleToString(bid, 5));
            }
        }
    }
}

//+------------------------------------------------------------------+
//| AÇIK POZİSYON KONTROLÜ                                           |
//+------------------------------------------------------------------+
void CheckOpenPositions(double ask, double bid)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(PositionGetSymbol(i) == _Symbol && 
           PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
        {
            ulong ticket = PositionGetTicket(i);
            long pos_type = PositionGetInteger(POSITION_TYPE);
            double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
            double current_sl = PositionGetDouble(POSITION_SL);
            double current_tp = PositionGetDouble(POSITION_TP);
            
            // Kar/Zarar hesapla
            double current_price = (pos_type == POSITION_TYPE_BUY) ? bid : ask;
            double profit_pct = ((current_price - open_price) / open_price) * 100.0;
            
            // Zarar durdurmayı kaldırma (Trailing Stop)
            if(profit_pct > 0.5 && current_sl > 0)
            {
                double new_sl = open_price + (open_price * 0.3 / 100.0);
                
                if((pos_type == POSITION_TYPE_BUY && new_sl > current_sl) ||
                   (pos_type == POSITION_TYPE_SELL && new_sl < current_sl))
                {
                    trade.PositionModify(ticket, new_sl, current_tp);
                }
            }
            
            // İstatistik güncelle
            if(profit_pct > 0) stats.wins++;
            else stats.losses++;
            stats.total_profit += profit_pct;
        }
    }
}

//+------------------------------------------------------------------+
//| TEKNIK ANDİKATÖRLER ANALİZİ                                      |
//+------------------------------------------------------------------+
int AnalyzeTechnicals(double &buy_prob, double &sell_prob)
{
    int strength = 0;
    
    double fast[], mid[], slow[], rsi_vals[];
    double macd_main[], macd_signal[], macd_hist[];
    double bb_upper[], bb_lower[];
    
    ArraySetAsSeries(fast, true);
    ArraySetAsSeries(mid, true);
    ArraySetAsSeries(slow, true);
    ArraySetAsSeries(rsi_vals, true);
    ArraySetAsSeries(macd_main, true);
    ArraySetAsSeries(macd_signal, true);
    ArraySetAsSeries(macd_hist, true);
    ArraySetAsSeries(bb_upper, true);
    ArraySetAsSeries(bb_lower, true);
    
    CopyBuffer(ema_fast, 0, 0, 3, fast);
    CopyBuffer(ema_mid, 0, 0, 3, mid);
    CopyBuffer(ema_slow, 0, 0, 3, slow);
    CopyBuffer(rsi_handle, 0, 0, 3, rsi_vals);
    CopyBuffer(macd_handle, 0, 0, 3, macd_main);
    CopyBuffer(macd_handle, 1, 0, 3, macd_signal);
    CopyBuffer(macd_handle, 2, 0, 3, macd_hist);
    CopyBuffer(bb_handle, 1, 0, 3, bb_upper);
    CopyBuffer(bb_handle, 2, 0, 3, bb_lower);
    
    // 🎯 EMA Çapraz Analizi
    if(fast[0] > mid[0] && mid[0] > slow[0])
    {
        buy_prob *= 1.2;
        strength += 2;
    }
    else if(fast[0] < mid[0] && mid[0] < slow[0])
    {
        sell_prob *= 1.2;
        strength += 2;
    }
    
    // 🎯 RSI Analizi
    if(rsi_vals[0] > 30 && rsi_vals[0] < 70)
    {
        if(rsi_vals[0] > 50 && buy_prob > sell_prob)
        {
            buy_prob *= 1.15;
            strength += 1;
        }
        else if(rsi_vals[0] < 50 && sell_prob > buy_prob)
        {
            sell_prob *= 1.15;
            strength += 1;
        }
    }
    
    // 🎯 MACD Analizi
    if(macd_main[0] > macd_signal[0] && macd_hist[0] > 0)
    {
        buy_prob *= 1.15;
        strength += 1;
    }
    else if(macd_main[0] < macd_signal[0] && macd_hist[0] < 0)
    {
        sell_prob *= 1.15;
        strength += 1;
    }
    
    // 🎯 Bollinger Bands
    if(candles[0].close < bb_lower[0])
    {
        buy_prob *= 1.1;
        strength += 1;
    }
    else if(candles[0].close > bb_upper[0])
    {
        sell_prob *= 1.1;
        strength += 1;
    }
    
    // Olasılıkları normalize et
    double total = buy_prob + sell_prob;
    buy_prob /= total;
    sell_prob /= total;
    
    return strength;
}

//+------------------------------------------------------------------+
//| AI TAHMİNİ (ONNX + Fallback)                                     |
//+------------------------------------------------------------------+
void GetAIPrediction(float &features[], double &buy_prob, double &sell_prob)
{
    // ONNX Model var mı kontrol et
    long onnx_handle = OnnxCreate("smart_model.onnx", ONNX_DEFAULT);
    
    if(onnx_handle != INVALID_HANDLE)
    {
        float output[];
        ArrayResize(output, 2);
        
        if(OnnxRun(onnx_handle, ONNX_DEFAULT, features, output))
        {
            sell_prob = output[0];
            buy_prob = output[1];
        }
        else
        {
            Print("⚠️ ONNX tahmin hatası");
        }
        
        OnnxRelease(onnx_handle);
    }
    else
    {
        // Fallback: Basit kurallar
        double fast[], mid[], slow[], rsi[];
        ArraySetAsSeries(fast, true);
        ArraySetAsSeries(mid, true);
        ArraySetAsSeries(slow, true);
        ArraySetAsSeries(rsi, true);
        
        CopyBuffer(ema_fast, 0, 0, 1, fast);
        CopyBuffer(ema_mid, 0, 0, 1, mid);
        CopyBuffer(ema_slow, 0, 0, 1, slow);
        CopyBuffer(rsi_handle, 0, 0, 1, rsi);
        
        if(global_trend_bias >= -0.1 && candles[0].close > slow[0] && 
           fast[0] > mid[0] && rsi[0] < 75)
        {
            buy_prob = 0.85;
            sell_prob = 0.15;
        }
        else if(global_trend_bias <= 0.1 && candles[0].close < slow[0] && 
                fast[0] < mid[0] && rsi[0] > 25)
        {
            buy_prob = 0.15;
            sell_prob = 0.85;
        }
        else
        {
            buy_prob = 0.50;
            sell_prob = 0.50;
        }
    }
}

//+------------------------------------------------------------------+
//| AKILLI ÖZELLİKLER HAZIRLA                                        |
//+------------------------------------------------------------------+
bool PrepareSmartFeatures(float &out_features[])
{
    int total_size = InpSequenceLength * InpFeatureCount;
    ArrayResize(out_features, total_size);
    
    double rsi_vals[], atr_vals[], volume_vals[];
    ArraySetAsSeries(rsi_vals, true);
    ArraySetAsSeries(atr_vals, true);
    ArraySetAsSeries(volume_vals, true);
    
    CopyBuffer(rsi_handle, 0, 0, InpSequenceLength, rsi_vals);
    CopyBuffer(atr_handle, 0, 0, InpSequenceLength, atr_vals);
    CopyBuffer(volume_handle, 0, 0, InpSequenceLength, volume_vals);
    
    int idx = 0;
    
    for(int i = 0; i < InpSequenceLength; i++)
    {
        // OHLCV
        out_features[idx++] = (float)candles[i].open;
        out_features[idx++] = (float)candles[i].high;
        out_features[idx++] = (float)candles[i].low;
        out_features[idx++] = (float)candles[i].close;
        out_features[idx++] = (float)candles[i].tick_volume;
        
        // Normalized Indicators
        out_features[idx++] = (float)(rsi_vals[i] / 100.0);
        out_features[idx++] = (float)(atr_vals[i] / 10.0);
        
        // Price Action
        float hl_ratio = (candles[i].close - candles[i].low) / 
                        (candles[i].high - candles[i].low + 0.00001f);
        out_features[idx++] = hl_ratio;
        
        // Momentum
        out_features[idx++] = (float)((candles[i].close - candles[i].open) / 
                                      (candles[i].high - candles[i].low + 0.00001f));
        
        // Volume Normalized
        double avg_volume = (i > 0) ? (volume_vals[i-1] + volume_vals[i]) / 2.0 : volume_vals[i];
        out_features[idx++] = (float)(volume_vals[i] / (avg_volume + 1.0));
        
        // Fill remaining features
        for(int f = 10; f < InpFeatureCount; f++)
        {
            float calc = hl_ratio * (f + 1.0f) * (1.0f - (float)(rsi_vals[i] / 100.0f));
            out_features[idx++] = calc;
        }
    }
    
    return true;
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
//| TİCARET SAATİ KONTROLü                                           |
//+------------------------------------------------------------------+
bool IsTradeTime()
{
    int hour = Hour();
    
    // NY seansı: 13:00 - 22:00 (GMT+3)
    if(InpUseNewYorkSession)
    {
        return (hour >= InpStartHour && hour < InpEndHour);
    }
    
    return true;
}
