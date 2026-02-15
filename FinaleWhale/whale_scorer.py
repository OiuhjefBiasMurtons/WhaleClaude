#!/usr/bin/env python3
"""
🦈 WHALE SCORER - Módulo compartido de scoring e inteligencia
Contiene la lógica de scoring, detección de bots y recomendaciones
usada por polywhale_batch y polywhale_v5_adjusted.

Sistema de scoring (100 puntos):
- Rentabilidad (35 pts): ROI, Profit Factor, PnL absoluto
- Consistencia (25 pts): Win Rate, ratio ganancia/pérdida promedio
- Gestión de Riesgo (20 pts): Drawdown máximo, diversificación
- Experiencia (20 pts): Antigüedad, volumen, ranking global
"""

# Niveles de Ballenas Configurables
WHALE_TIERS = [
    (40000, "🐋🐋🐋🐋🐋", "TITAN BALLENA"),
    (20000, "🐋🐋🐋🐋", "ULTRA BALLENA"),
    (10000, "🐋🐋🐋", "MEGA BALLENA"),
    (5000, "🐋🐋", "BALLENA GRANDE"),
    (2000, "🐋", "BALLENA"),
    (0, "🦈", "TIBURÓN")
]


class WhaleScorer:
    """
    Mixin con métodos de scoring compartidos.
    Las clases que hereden deben inicializar:
      self.scraped_data, self.scores, self.red_flags, self.strengths
    """

    def calculate_profitability_score(self):
        """
        RENTABILIDAD (35 puntos) - AJUSTADO [+5 pts]
        - ROI efectivo (15 pts) [+3]
        - Profit Factor (12 pts) [+2]
        - PnL absoluto (8 pts) [igual]
        """
        score = 0
        d = self.scraped_data

        # 1. ROI = PnL / (Gains + Losses) * 100
        pnl = d.get('pnl', 0)
        total_traded = d.get('total_gains', 0) + d.get('total_losses', 0)

        if total_traded > 0:
            roi = (pnl / total_traded) * 100
            self.roi = roi

            # ✅ AJUSTE: Umbrales más realistas + bonificación a rango 10-25%
            if roi > 25:  # Era >30
                score += 15  # Era 12
                self.strengths.append(f"✓ ROI excepcional: {roi:.1f}%")
            elif roi > 18:  # Era >20
                score += 13  # Era 10
                self.strengths.append(f"✓ ROI excelente: {roi:.1f}%")
            elif roi > 13:  # Era >15
                score += 11  # Era 8, ahora 11 (+3)
                self.strengths.append(f"✓ ROI muy bueno: {roi:.1f}%")
            elif roi > 10:  # NUEVO: reconocer ROI >10%
                score += 9  # Era 8, ahora 9 (+1)
                self.strengths.append(f"✓ ROI sólido: {roi:.1f}%")
            elif roi > 7:  # Era >9
                score += 7  # Era 8, ahora 7 (-1)
            elif roi > 5:
                score += 5  # Igual
            elif roi > 2:  # Era >0
                score += 3  # Era 2
            elif roi > 0:
                score += 1
            elif roi < -10:
                self.red_flags.append(f"⚠️ ROI negativo: {roi:.1f}%")

        # 2. Profit Factor = Gains / Losses
        profit_factor = d.get('profit_factor', 0)
        self.profit_factor = profit_factor

        # ✅ AJUSTE: Umbrales más alcanzables + bonificación al rango 1.2-2.0x
        if profit_factor > 2.8:  # Era >3.0
            score += 12  # Era 10
            self.strengths.append(f"✓ Profit Factor elite: {profit_factor:.2f}")
        elif profit_factor > 2.3:  # Era >2.5
            score += 10  # Era 9
            self.strengths.append(f"✓ Profit Factor excelente: {profit_factor:.2f}")
        elif profit_factor > 1.9:  # Era >2.0
            score += 8  # Era 7
        elif profit_factor > 1.5:
            score += 7  # Era 5, ahora 7 (+2)
        elif profit_factor > 1.2:
            score += 5  # Era 3, ahora 5 (+2) ← Aquí entra Predictoor99
            self.strengths.append(f"✓ Profit Factor positivo: {profit_factor:.2f}")
        elif profit_factor > 1.0:
            score += 2  # Era 1
            score += 2  # Era 1
        elif profit_factor < 1.0:
            self.red_flags.append(f"⚠️ Profit Factor < 1: {profit_factor:.2f}")

        # 3. PnL Absoluto (tamaño del éxito) - SIN CAMBIOS
        if pnl > 100000:
            score += 8
        elif pnl > 50000:
            score += 6
        elif pnl > 20000:
            score += 4
        elif pnl > 5000:
            score += 2
        elif pnl > 0:
            score += 1

        self.scores['profitability'] = min(score, 35)
        return self.scores['profitability']

    def calculate_consistency_score(self):
        """
        CONSISTENCIA (25 puntos) - AJUSTADO
        - Win Rate (12 pts) [umbrales suavizados]
        - Ratio Avg Win / Avg Loss (8 pts)
        - Distribución de ganancias (5 pts)
        """
        score = 0
        d = self.scraped_data

        # 1. Win Rate - ✅ AJUSTE: Umbrales más realistas
        win_rate = d.get('win_rate', 0)
        self.win_rate = win_rate

        if win_rate > 70:  # Era >75
            score += 12
            self.strengths.append(f"✓ Win Rate excepcional: {win_rate:.1f}%")
        elif win_rate > 62:  # Era >67
            score += 10
            self.strengths.append(f"✓ Win Rate alto: {win_rate:.1f}%")
        elif win_rate > 57:  # Era >60
            score += 8
        elif win_rate > 52:  # Era >55
            score += 6
        elif win_rate > 48:  # Era >50
            score += 4
        elif win_rate > 43:  # Era >45
            score += 2
        elif win_rate < 40:
            self.red_flags.append(f"⚠️ Win Rate bajo: {win_rate:.1f}%")

        # 2. Ratio Avg Win / Avg Loss - SIN CAMBIOS
        avg_win = d.get('avg_win', 0)
        avg_loss = d.get('avg_loss', 1)

        if avg_loss > 0:
            win_loss_ratio = avg_win / avg_loss
            self.win_loss_ratio = win_loss_ratio

            if win_loss_ratio > 2.0:
                score += 8
                self.strengths.append(f"✓ Ganancias 2x mayores que pérdidas")
            elif win_loss_ratio > 1.5:
                score += 6
            elif win_loss_ratio > 1.2:
                score += 4
            elif win_loss_ratio > 1.0:
                score += 2
            elif win_loss_ratio < 0.8:
                self.red_flags.append(f"⚠️ Pérdidas promedio mayores que ganancias")

        # 3. Distribución de ganancias - SIN CAMBIOS
        wins = d.get('biggest_wins', [])
        if len(wins) >= 3 and d.get('total_gains', 0) > 0:
            top_win = wins[0]['amount'] if wins else 0
            total_gains = d.get('total_gains', 1)
            concentration = top_win / total_gains

            if concentration < 0.2:
                score += 5
                self.strengths.append("✓ Ganancias bien distribuidas")
            elif concentration < 0.3:
                score += 4
            elif concentration < 0.4:
                score += 2
            elif concentration > 0.5:
                self.red_flags.append(f"⚠️ {concentration*100:.0f}% de ganancias en 1 trade")

        self.scores['consistency'] = min(score, 25)
        return self.scores['consistency']

    def calculate_risk_management_score(self):
        """
        GESTIÓN DE RIESGO (20 puntos) - AJUSTADO [-5 pts]
        - Control de pérdidas máximas (10 pts) [-2]
        - Diversificación por categoría (6 pts) [-2]
        - Ratio PnL / Max Loss (4 pts) [-1]
        """
        score = 0
        d = self.scraped_data

        # 1. Control de pérdidas máximas - ✅ AJUSTE: Menos puntos pero mismos umbrales
        max_loss = d.get('max_loss', 0)
        total_losses = d.get('total_losses', 1)
        pnl = d.get('pnl', 0)

        if total_losses > 0 and max_loss > 0:
            loss_concentration = max_loss / total_losses
            self.max_loss = max_loss
            self.loss_concentration = loss_concentration

            if loss_concentration < 0.15:
                score += 10  # Era 12
                self.strengths.append("✓ Pérdidas bien controladas")
            elif loss_concentration < 0.25:
                score += 8  # Era 9
            elif loss_concentration < 0.35:
                score += 5  # Era 6
            elif loss_concentration < 0.5:
                score += 2  # Era 3
            else:
                self.red_flags.append(f"⚠️ {loss_concentration*100:.0f}% de pérdidas en 1 trade")

        # 2. Diversificación por categoría - ✅ AJUSTE: Menos estricto
        categories = d.get('categories', [])
        if len(categories) >= 2:
            if len(categories) >= 5:
                score += 6  # Era 8
                self.strengths.append(f"✓ Opera en {len(categories)} categorías")
            elif len(categories) >= 3:
                score += 4  # Era 5
            elif len(categories) >= 2:
                score += 2  # Igual
        else:
            self.red_flags.append("⚠️ Solo opera en 1 categoría")

        # 3. Ratio PnL / Max Loss - ✅ AJUSTE: Menos puntos
        if max_loss > 0:
            risk_reward = pnl / max_loss
            self.risk_reward_ratio = risk_reward

            if risk_reward > 10:
                score += 4  # Era 5
            elif risk_reward > 5:
                score += 3  # Era 4
            elif risk_reward > 3:
                score += 2  # Era 3
            elif risk_reward > 1:
                score += 1  # Igual

        self.scores['risk_management'] = min(score, 20)
        return self.scores['risk_management']

    def calculate_experience_score(self):
        """
        EXPERIENCIA (20 puntos) - SIN CAMBIOS
        - Antigüedad y badges (8 pts)
        - Ranking global (7 pts)
        - Volumen operado (5 pts)
        """
        score = 0
        d = self.scraped_data

        # 1. Badges de experiencia
        badges = d.get('badges', [])

        if 'veteran' in badges:
            score += 5
            self.strengths.append("✓ Cuenta con más de 1 año")

        if 'pnl_100k' in badges:
            score += 3
        elif 'pnl_10k' in badges:
            score += 2

        # 2. Ranking global
        rank = d.get('rank', 999999)
        self.rank = rank

        if rank <= 100:
            score += 7
            self.strengths.append(f"✓ Top 100 global (#{rank})")
        elif rank <= 500:
            score += 6
            self.strengths.append(f"✓ Top 500 global (#{rank})")
        elif rank <= 1000:
            score += 5
        elif rank <= 2500:
            score += 3
        elif rank <= 5000:
            score += 2
        elif rank <= 10000:
            score += 1

        # 3. Volumen operado (total_gains + total_losses)
        total_traded = d.get('total_gains', 0) + d.get('total_losses', 0)
        self.total_traded = total_traded

        if total_traded > 500000:
            score += 5
        elif total_traded > 200000:
            score += 4
        elif total_traded > 100000:
            score += 3
        elif total_traded > 50000:
            score += 2
        elif total_traded > 10000:
            score += 1

        self.scores['experience'] = min(score, 20)
        return self.scores['experience']

    def detect_bot_behavior(self):
        """
        🤖 DETECCIÓN DE BOTS
        Analiza múltiples indicadores para determinar si es un bot/MM

        Indicadores:
        1. Trades/Market ratio (>50 trades por mercado = bot)
        2. Frecuencia extrema (>7000 trades totales)
        3. Profit Factor muy bajo + volumen alto (market maker)
        4. Volumen extremo con pocos mercados (>4000 trades en <50 mercados)
        """
        d = self.scraped_data
        is_bot = False
        bot_confidence = 0  # 0-100%
        bot_reasons = []

        total_trades = d.get('total_trades', 0)
        markets_traded = d.get('markets_traded', 0)
        total_volume = d.get('total_gains', 0) + d.get('total_losses', 0)
        profit_factor = d.get('profit_factor', 0)

        # INDICADOR 1: Trades por mercado (bots hacen muchos trades en pocos mercados)
        if markets_traded > 0 and total_trades > 0:
            trades_per_market = total_trades / markets_traded

            if trades_per_market > 50:  # Era >100
                is_bot = True
                bot_confidence += 40
                bot_reasons.append(f"🤖 {trades_per_market:.0f} trades/mercado (bot confirmado)")
            elif trades_per_market > 25:  # Era >50
                bot_confidence += 30
                bot_reasons.append(f"⚠️ {trades_per_market:.0f} trades/mercado (posible bot)")
            elif trades_per_market > 15:  # Era >30
                bot_confidence += 15
                bot_reasons.append(f"⚡ {trades_per_market:.0f} trades/mercado (alta frecuencia)")

        # INDICADOR 2: Volumen extremo con pocos mercados
        if total_trades > 4000 and markets_traded < 50:  # Era >5000
            is_bot = True
            bot_confidence += 30
            bot_reasons.append(f"🤖 {total_trades:,} trades en solo {markets_traded} mercados")

        # INDICADOR 3: Volumen muy alto con profit factor cercano a 1 (market maker)
        if total_volume > 1000000 and 0.95 < profit_factor < 1.05:
            is_bot = True
            bot_confidence += 35
            bot_reasons.append(f"🤖 Market Maker (PF={profit_factor:.2f}, Vol=${total_volume/1e6:.1f}M)")

        # INDICADOR 4: Frecuencia absurda
        if total_trades > 7000:  # Era >10000
            is_bot = True
            bot_confidence += 50
            bot_reasons.append(f"🤖 Frecuencia extrema ({total_trades:,} trades)")

        # INDICADOR 5: Win rate exactamente 50% con alto volumen (bot arbitrajista)
        win_rate = d.get('win_rate', 0)
        if 49.5 <= win_rate <= 50.5 and total_volume > 500000:
            bot_confidence += 25
            bot_reasons.append(f"⚠️ Win Rate sospechoso (50% exacto con alto volumen)")

        # ✅ INDICADOR 6: Hiperactividad (muchos trades + muchos mercados)
        if total_trades > 3000 and markets_traded > 100:
            is_bot = True
            bot_confidence += 35
            bot_reasons.append(f"🤖 Hiperactividad: {total_trades:,} trades en {markets_traded} mercados")

        # ✅ INDICADOR 7: Threshold más bajo para confirmación múltiple
        if total_trades > 2000 and markets_traded > 0:
            tpm = total_trades / markets_traded
            if tpm > 15:
                bot_confidence += 20
                bot_reasons.append(f"⚠️ Volumen sospechoso: {total_trades:,} trades con {tpm:.0f} t/m")

        # ✅ INDICADOR 8: Detección heurística cuando faltan datos
        if total_trades == 0 and total_volume > 10000000:
            if profit_factor < 0.9:
                bot_confidence += 25
                bot_reasons.append(f"⚠️ Volumen extremo ${total_volume/1e6:.1f}M con PF bajo (posible bot)")

            rank = d.get('rank', 0)
            if rank > 500000 and total_volume > 10000000:
                is_bot = True
                bot_confidence += 35
                bot_reasons.append(f"🤖 Ranking #{rank:,} con ${total_volume/1e6:.1f}M operados (patrón bot)")

        # ✅ INDICADOR 9: Bot perdedor con volumen medio-alto
        if total_trades == 0 and total_volume > 5000000:
            rank = d.get('rank', 0)
            pnl = d.get('pnl', 0)

            if rank > 1000000 and pnl < -500000:
                is_bot = True
                bot_confidence += 30
                bot_reasons.append(f"🤖 Bot perdedor: Ranking #{rank:,}, PnL ${pnl/1e6:.1f}M, Vol ${total_volume/1e6:.1f}M")
            elif rank > 1000000 and profit_factor < 0.85:
                bot_confidence += 25
                bot_reasons.append(f"⚠️ Patrón sospechoso: Ranking #{rank:,}, PF {profit_factor:.2f}, Vol ${total_volume/1e6:.1f}M")

        # ✅ INDICADOR 10: Ratio Volumen/PnL extremo
        if total_trades == 0 and total_volume > 10000000:
            pnl = d.get('pnl', 0)
            if pnl > 0:
                volume_pnl_ratio = total_volume / pnl

                if volume_pnl_ratio > 15:
                    is_bot = True
                    bot_confidence += 45
                    bot_reasons.append(f"🤖 Ratio Vol/PnL extremo: {volume_pnl_ratio:.1f}x (patrón MM/bot)")
                elif volume_pnl_ratio > 10:
                    is_bot = True
                    bot_confidence += 35
                    bot_reasons.append(f"🤖 Ratio Vol/PnL alto: {volume_pnl_ratio:.1f}x (patrón bot)")
                elif volume_pnl_ratio > 8:
                    bot_confidence += 30
                    bot_reasons.append(f"⚠️ Ratio Vol/PnL elevado: {volume_pnl_ratio:.1f}x (posible bot)")
                elif volume_pnl_ratio > 6:
                    bot_confidence += 20
                    bot_reasons.append(f"⚡ Ratio Vol/PnL sospechoso: {volume_pnl_ratio:.1f}x (alta frecuencia)")

        # ✅ INDICADOR 11: Top ranking con PnL bajo relativo
        if total_trades == 0:
            rank = d.get('rank', 999999)
            pnl = d.get('pnl', 0)

            if rank <= 10 and 0 < pnl < 10000000 and total_volume > 50000000:
                is_bot = True
                bot_confidence += 45
                bot_reasons.append(f"🤖 Top #{rank} con PnL ${pnl/1e6:.1f}M vs Vol ${total_volume/1e6:.1f}M (bot confirmado)")
            elif rank <= 20 and 0 < pnl < 5000000 and total_volume > 20000000:
                is_bot = True
                bot_confidence += 35
                bot_reasons.append(f"🤖 Top #{rank} con PnL ${pnl/1e6:.1f}M vs Vol ${total_volume/1e6:.1f}M (patrón bot)")
            elif rank <= 50 and 0 < pnl < 3000000 and total_volume > 25000000:
                bot_confidence += 30
                bot_reasons.append(f"⚠️ Top #{rank} con bajo PnL relativo (posible bot)")
            elif rank <= 100 and 0 < pnl < 2000000 and total_volume > 30000000:
                bot_confidence += 25
                bot_reasons.append(f"⚡ Ranking #{rank} con volumen desproporcionado (alta frecuencia)")

        # ✅ INDICADOR 12: Win Rate cercano a 50% + alto volumen
        if total_trades == 0 and total_volume > 20000000:
            win_rate = d.get('win_rate', 0)
            if 50 <= win_rate <= 55:
                bot_confidence += 25
                bot_reasons.append(f"⚠️ Win Rate {win_rate:.1f}% cercano a 50% con alto volumen (patrón bot)")

        # ✅ INDICADOR 13: Top ranking con ROI bajo
        if total_trades == 0:
            rank = d.get('rank', 999999)
            pnl = d.get('pnl', 0)

            if pnl > 0 and total_volume > 0:
                roi = (pnl / total_volume) * 100

                if rank <= 10 and roi < 10:
                    is_bot = True
                    bot_confidence += 40
                    bot_reasons.append(f"🤖 Top #{rank} con ROI {roi:.1f}% (bot por volumen, no skill)")
                elif rank <= 20 and roi < 12:
                    bot_confidence += 30
                    bot_reasons.append(f"⚠️ Top #{rank} con ROI {roi:.1f}% bajo (posible bot)")

        # ✅ INDICADOR 14: Profit Factor bajo + alto volumen
        if total_trades == 0 and total_volume > 30000000:
            profit_factor = d.get('profit_factor', 0)
            if 1.1 < profit_factor < 1.3:
                bot_confidence += 25
                bot_reasons.append(f"⚠️ Profit Factor {profit_factor:.2f}x bajo con alto volumen (patrón MM)")

        # Guardar resultados
        self.is_bot = is_bot
        self.bot_confidence = min(bot_confidence, 100)
        self.bot_reasons = bot_reasons

        # Agregar a red flags si es bot
        if is_bot:
            confidence_text = "ALTA" if bot_confidence > 70 else "MEDIA" if bot_confidence > 40 else "BAJA"
            self.red_flags.insert(0, f"🤖 POSIBLE BOT/MM (confianza {confidence_text}: {bot_confidence}%)")

        return is_bot

    def calculate_final_score(self):
        """Calcula score final y determina tier/grade"""
        total = (self.scores['profitability'] +
                self.scores['consistency'] +
                self.scores['risk_management'] +
                self.scores['experience'])

        self.scores['total'] = total

        # ✅ Determinar si es bot ANTES de asignar tier
        is_bot = self.detect_bot_behavior()

        # ⚠️ PENALIZACIÓN POR BOT
        if is_bot:
            # Penalización proporcional a la confianza
            penalty = int(self.bot_confidence * 0.3)  # Max 30 pts de penalización
            total = max(0, total - penalty)
            self.scores['total'] = total
            self.scores['bot_penalty'] = penalty

        # Determinar Tier
        if is_bot and self.bot_confidence > 80:
            self.scores['tier'] = "🤖 BOT/MM"
            self.scores['reliability_grade'] = "N/A"
        elif total >= 85:
            self.scores['tier'] = "💎 DIAMOND"
            self.scores['reliability_grade'] = "A+"
        elif total >= 75:
            self.scores['tier'] = "🥇 GOLD"
            self.scores['reliability_grade'] = "A"
        elif total >= 65:
            self.scores['tier'] = "🥈 SILVER"
            self.scores['reliability_grade'] = "B+"
        elif total >= 55:
            self.scores['tier'] = "🥉 BRONZE"
            self.scores['reliability_grade'] = "B"
        elif total >= 45:
            self.scores['tier'] = "📊 STANDARD"
            self.scores['reliability_grade'] = "C"
        elif total >= 35:
            self.scores['tier'] = "⚠️ RISKY"
            self.scores['reliability_grade'] = "D"
        else:
            self.scores['tier'] = "💀 HIGH RISK"
            self.scores['reliability_grade'] = "F"

        return total

    def generate_recommendation(self):
        """Genera recomendación basada en el análisis"""
        total = self.scores['total']

        # ⚠️ ADVERTENCIA ESPECIAL PARA BOTS
        if getattr(self, 'is_bot', False):
            if self.bot_confidence > 80:
                return "🤖 BOT/MARKET MAKER DETECTADO - NO RECOMENDADO para copiar. Patrón de trading automatizado."
            elif self.bot_confidence > 50:
                return "⚠️ POSIBLE BOT - Alta sospecha de trading automatizado. NO copiar sin investigar."
            else:
                return "⚠️ ADVERTENCIA: Señales de trading automatizado detectadas. Verificar manualmente."

        # Recomendaciones normales
        if total >= 85:
            return "✅ ALTAMENTE CONFIABLE - Trader elite con historial excepcional. Ideal para seguir."
        elif total >= 75:
            return "✅ MUY CONFIABLE - Excelente balance riesgo/retorno. Recomendado para copiar."
        elif total >= 65:
            return "✅ CONFIABLE - Buen rendimiento consistente. Copiar con posiciones moderadas."
        elif total >= 55:
            return "⚠️ MODERADO - Resultados aceptables pero revisar red flags antes de copiar."
        elif total >= 45:
            return "⚠️ PRECAUCIÓN - Solo para seguimiento. No recomendado para copiar directamente."
        elif total >= 35:
            return "❌ NO RECOMENDADO - Alto riesgo o inconsistencia significativa."
        else:
            return "❌ EVITAR - Resultados negativos o perfil de alto riesgo."
