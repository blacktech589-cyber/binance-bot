//+------------------------------------------------------------------+
//|                                SafeScalperPro_H1_Spread40.mq5    |
//|                                  Copyright 2026, Deep Learning   |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026"
#property link      "https://www.mql5.com"
#property version   "21.01"
#property strict

#include <Trade\Trade.mqh>
CTrade trade;

input group "--- 80K Geçmiş Analiz & Bellek Yönetimi ---"
input int      InpHistoryScanCount = 80000;  // Başlangıçta analiz edilecek maksimum geçmiş mum
input int      InpSequenceLength   = 50;       // Anlık yapay zeka hafıza derinliği
input int      InpFeatureCount     = 25;       // Özellik derinliği (Özel İstek: 25 Girdi)
input double   InpConfidence       = 0.85;     // Güven eşiği
input double   InpMaxAllowedATR    = 20.0;     // Maksimum Volatilite Sınırı

input group "--- İşlem, Lot ve Sabit Risk Yönetimi ---"
input double   InpLotSize          = 0.01;     // Minimum Lot Miktarı (0.01)
input double   InpRiskUSD          = 10.0;     // İşlem Başına Sabit Risk ($10)
input double   InpTakeProfit       = 0.20;     // Hızlı Kâr Hedefi (0.20)
input int      InpMaxSpread        = 40;       // (GÜNCELLENDİ) Maksimum Spread Sınırı (40 Puan)
input int      InpMaxTrades        = 1;        // Aynı anda tek pozisyon
input ulong    InpMagicNumber      = 778899;   // Sihirli Numara

long ext_onnx_handle = INVALID_HANDLE;
int rsi_handle = INVALID_HANDLE;
int atr_handle = INVALID_HANDLE;
int ema_fast_handle = INVALID_HANDLE;
int ema_slow_handle = INVALID_HANDLE;
int h1_ma_handle    = INVALID_HANDLE;

MqlRates memory_candles[];
double global_longterm_trend_bias = 0.0; 

//+------------------------------------------------------------------+
//| Expert initialization function - 80K GEÇMİŞ ANALİZİ              |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   
   MqlRates historic_rates[];
   ArraySetAsSeries(historic_rates, true);
   
   int available_bars = CopyRates(_Symbol, PERIOD_H1, 0, InpHistoryScanCount, historic_rates);
   if(available_bars > 0)
   {
      Print("📊 Başarılı: H1 grafiğinden ", available_bars, " adet mum yüklendi ve analiz ediliyor...");
      
      double sum_close = 0;
      double highest_price = historic_rates[0].high;
      double lowest_price = historic_rates[0].low;
      
      for(int i = 0; i < available_bars; i++)
      {
         sum_close += historic_rates[i].close;
         if(historic_rates[i].high > highest_price) highest_price = historic_rates[i].high;
         if(historic_rates[i].low < lowest_price) lowest_price = historic_rates[i].low;
      }
      
      double average_price = sum_close / (double)available_bars;
      double current_close = historic_rates[0].close;
      
      global_longterm_trend_bias = (current_close - average_price) / (highest_price - lowest_price + 0.00001);
      Print("📈 80K Analiz Tamamlandı. Uzun Vadeli Trend Eğilim Skoru: ", global_longterm_trend_bias);
   }
   else
   {
      Print("⚠️ Uyarı: Yeterli H1 geçmiş mumu bulunamadı, varsayılan ayarlarla devam ediliyor.");
   }

   ext_onnx_handle = OnnxCreate("xauusd_deep_model.onnx", ONNX_DEFAULT);
   if(ext_onnx_handle == INVALID_HANDLE)
   {
      Print("Bilgi: ONNX modeli bulunamadı. Simülasyon Devrede.");
   }
   else
   {
      long input_shape[] = {1, InpSequenceLength, InpFeatureCount};
      OnnxSetInputShape(ext_onnx_handle, 0, input_shape);
      long output_shape[] = {1, 2};
      OnnxSetOutputShape(ext_onnx_handle, 0, output_shape);
   }

   rsi_handle      = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE);
   atr_handle      = iATR(_Symbol, PERIOD_H1, 14);
   ema_fast_handle = iMA(_Symbol, PERIOD_H1, 9, 0, MODE_EMA, PRICE_CLOSE);
   ema_slow_handle = iMA(_Symbol, PERIOD_H1, 21, 0, MODE_EMA, PRICE_CLOSE);
   h1_ma_handle    = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);

   if(rsi_handle == INVALID_HANDLE || atr_handle == INVALID_HANDLE || 
      ema_fast_handle == INVALID_HANDLE || ema_slow_handle == INVALID_HANDLE || h1_ma_handle == INVALID_HANDLE)
      return(INIT_FAILED);

   ArrayResize(memory_candles, InpSequenceLength + 10);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(ext_onnx_handle != INVALID_HANDLE) OnnxRelease(ext_onnx_handle);
   IndicatorRelease(rsi_handle);
   IndicatorRelease(atr_handle);
   IndicatorRelease(ema_fast_handle);
   IndicatorRelease(ema_slow_handle);
   IndicatorRelease(h1_ma_handle);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   // 1. ÇOK HIZLI KÂR (TP) KAPATMA KONTROLÜ
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
      {
         ulong ticket = PositionGetTicket(i);
         long pos_type = PositionGetInteger(POSITION_TYPE);
         double open_price = PositionGetDouble(POSITION_PRICE_OPEN);

         if(pos_type == POSITION_TYPE_BUY && bid >= open_price + InpTakeProfit)
         {
            trade.PositionClose(ticket);
            Print("⚡ Hızlı Kâr Alındı! H1 Alış pozisyonu kapatıldı.");
            return;
         }
         else if(pos_type == POSITION_TYPE_SELL && ask <= open_price - InpTakeProfit)
         {
            trade.PositionClose(ticket);
            Print("⚡ Hızlı Kâr Alındı! H1 Satış pozisyonu kapatıldı.");
            return;
         }
      }
   }

   // 2. Spread Kontrolü (40 Puan)
   long current_spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(current_spread > InpMaxSpread) return;

   // 3. ATR Volatilite Kontrolü
   double atr_vals[];
   ArraySetAsSeries(atr_vals, true);
   if(CopyBuffer(atr_handle, 0, 0, 1, atr_vals) > 0)
   {
      if(atr_vals[0] > InpMaxAllowedATR) return; 
   }

   if(!UpdateCandleMemory()) return;

   float input_data[];
   if(!PrepareFeatureMatrix(input_data)) return;

   double buy_probability = 0.5;
   double sell_probability = 0.5;

   if(ext_onnx_handle != INVALID_HANDLE)
   {
      float output_data[];
      ArrayResize(output_data, 2);
      if(OnnxRun(ext_onnx_handle, ONNX_DEFAULT, input_data, output_data))
      {
         sell_probability = output_data[0];
         buy_probability  = output_data[1];
      }
   }
   else
   {
      double fast_ma[], slow_ma[], h1_ma[], rsi_vals[];
      ArraySetAsSeries(fast_ma, true);
      ArraySetAsSeries(slow_ma, true);
      ArraySetAsSeries(h1_ma, true);
      ArraySetAsSeries(rsi_vals, true);
      
      CopyBuffer(ema_fast_handle, 0, 0, 2, fast_ma);
      CopyBuffer(ema_slow_handle, 0, 0, 2, slow_ma);
      CopyBuffer(h1_ma_handle, 0, 0, 2, h1_ma);
      CopyBuffer(rsi_handle, 0, 0, 2, rsi_vals);

      bool safe_bullish = (global_longterm_trend_bias >= -0.1 && memory_candles[0].close > h1_ma[0] && fast_ma[0] > slow_ma[0] && rsi_vals[0] < 75);
      bool safe_bearish = (global_longterm_trend_bias <= 0.1 && memory_candles[0].close < h1_ma[0] && fast_ma[0] < slow_ma[0] && rsi_vals[0] > 25);

      if(safe_bullish)  { buy_probability = 0.90; sell_probability = 0.10; }
      else if(safe_bearish) { buy_probability = 0.10; sell_probability = 0.90; }
      else              { buy_probability = 0.50; sell_probability = 0.50; }
   }

   bool is_buy_signal = (buy_probability >= InpConfidence);
   bool is_sell_signal = (sell_probability >= InpConfidence);

   double price_risk_distance = InpRiskUSD / (InpLotSize * 100.0);
   int open_positions = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
      {
         open_positions++;
         ulong ticket = PositionGetTicket(i);
         long pos_type = PositionGetInteger(POSITION_TYPE);

         if(pos_type == POSITION_TYPE_BUY && is_sell_signal)
         {
            trade.PositionClose(ticket);
            double sl = bid + price_risk_distance;
            trade.Sell(InpLotSize, _Symbol, bid, sl, 0, "Flip Sell");
            return;
         }
         else if(pos_type == POSITION_TYPE_SELL && is_buy_signal)
         {
            trade.PositionClose(ticket);
            double sl = ask - price_risk_distance;
            trade.Buy(InpLotSize, _Symbol, ask, sl, 0, "Flip Buy");
            return;
         }
      }
   }

   if(open_positions < InpMaxTrades)
   {
      if(is_buy_signal)
      {
         double sl = ask - price_risk_distance;
         trade.Buy(InpLotSize, _Symbol, ask, sl, 0, "H1 Buy");
      }
      else if(is_sell_signal)
      {
         double sl = bid + price_risk_distance;
         trade.Sell(InpLotSize, _Symbol, bid, sl, 0, "H1 Sell");
      }
   }
}

bool UpdateCandleMemory()
{
   MqlRates temp_rates[];
   ArraySetAsSeries(temp_rates, true);
   
   if(CopyRates(_Symbol, PERIOD_H1, 0, InpSequenceLength + 5, temp_rates) < InpSequenceLength)
      return false;

   ArrayResize(memory_candles, InpSequenceLength);
   ArrayCopy(memory_candles, temp_rates, 0, 0, InpSequenceLength);
   return true;
}

bool PrepareFeatureMatrix(float &out_matrix[])
{
   int total_size = InpSequenceLength * InpFeatureCount;
   ArrayResize(out_matrix, total_size);

   double rsi_vals[], atr_vals[];
   ArraySetAsSeries(rsi_vals, true);
   ArraySetAsSeries(atr_vals, true);

   CopyBuffer(rsi_handle, 0, 0, InpSequenceLength, rsi_vals);
   CopyBuffer(atr_handle, 0, 0, InpSequenceLength, atr_vals);

   int index = 0;
   for(int i = 0; i < InpSequenceLength; i++)
   {
      float o = (float)memory_candles[i].open;
      float h = (float)memory_candles[i].high;
      float l = (float)memory_candles[i].low;
      float c = (float)memory_candles[i].close;
      float v = (float)memory_candles[i].tick_volume;

      out_matrix[index++] = o;
      out_matrix[index++] = h;
      out_matrix[index++] = l;
      out_matrix[index++] = c;
      out_matrix[index++] = v;

      float r = (i < ArraySize(rsi_vals)) ? (float)rsi_vals[i] / 100.0f : 0.5f;
      float a = (i < ArraySize(atr_vals)) ? (float)atr_vals[i] / 10.0f : 1.0f;

      out_matrix[index++] = r;
      out_matrix[index++] = a;
      out_matrix[index++] = c; 
      out_matrix[index++] = c; 
      out_matrix[index++] = 0.0f;

      for(int f = 10; f < InpFeatureCount; f++)
      {
         float calculated_feature = ((c - l) / (h - l + 0.00001f)) * (float)(f + 1) * (1.0f - r);
         out_matrix[index++] = calculated_feature;
      }
   }
   return true;
}
