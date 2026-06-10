import logging
from sniperbot.strategy.swing_points import SwingPoint

logger = logging.getLogger(__name__)


class Zonation:
    PREMIUM = "premium"
    DISCOUNT = "discount"

    def __init__(self, min_range_dollars: float = 100.0, point_value: float = 20.0):
        # Converte i dollari in punti indice NQ (100.0 / 20.0 = 5.0 punti)
        self.min_range_points = min_range_dollars / point_value  
        
        # Inizializziamo le variabili di stato pubbliche per renderle accessibili a main.py
        self.range_top = None
        self.range_bottom = None
        self.midpoint = None

    def determine(self, price: float, swing_points: list[SwingPoint]) -> str | None:
        if not swing_points:
            logger.info("Zonation: nessun punto di swing disponibile")
            return None

        # Ordiniamo tutti gli swing rilevati dal più recente al più vecchio (in base al timestamp)
        recent_swings = sorted(swing_points, key=lambda s: s.timestamp, reverse=True)

        significant_high = None
        significant_low = None

        # Scansioniamo a ritroso gli swing per trovare la coppia High/Low più vicina con range >= 100$
        for s in recent_swings:
            if s.type == "high" and significant_high is None:
                significant_high = s.price
            elif s.type == "low" and significant_low is None:
                significant_low = s.price

            # Appena abbiamo un candidato massimo e un candidato minimo, verifichiamo l'escursione
            if significant_high is not None and significant_low is not None:
                range_amplitude = abs(significant_high - significant_low)
                
                if range_amplitude >= self.min_range_points:
                    # Abbiamo trovato il Dealing Range valido di almeno 100$! Usciamo dal ciclo.
                    break
                else:
                    # Se la distanza tra questo High e Low è inferiore a 100$, azzeriamo 
                    # lo swing più vecchio tra i due per cercare più indietro nel tempo
                    if s.type == "high":
                        significant_high = None
                    else:
                        significant_low = None

        # Se abbiamo esplorato lo storico senza trovare due punti idonei distanti almeno 100$
        if significant_high is None or significant_low is None:
            logger.info(f"Zonation: impossibile definire un range valido di almeno 100$ con gli swing attuali")
            return None

        # Salviamo i valori strutturali sull'istanza (self) per renderli accessibili all'esterno (es. main.py)
        self.range_top = significant_high
        self.range_bottom = significant_low
        self.midpoint = (self.range_top + self.range_bottom) / 2  # Equilibrio (Fibonacci 0.5)

        logger.info(
            f"Zonation (Range 100$+): top={self.range_top:.2f} mid={self.midpoint:.2f} bottom={self.range_bottom:.2f} "
            f"price={price:.2f} -> "
            f"{'PREMIUM' if self.midpoint < price < self.range_top else 'DISCOUNT' if self.range_bottom < price < self.midpoint else 'OUT OF RANGE'}"
        )

        # Premium: metà superiore (valuta solo SHORT)
        if self.midpoint < price < self.range_top:
            return self.PREMIUM

        # Discount: metà inferiore (valuta solo LONG)
        if self.range_bottom < price < self.midpoint:
            return self.DISCOUNT

        return None

    def allowed_direction(self, zone: str | None) -> str | None:
        if zone == self.PREMIUM:
            return "short"
        elif zone == self.DISCOUNT:
            return "long"
        return None