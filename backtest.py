import csv
import json


class Backtest:
    def __init__(self, price_history_filename, user_behavior_filename):
        f = open(price_history_filename)
        reader = csv.DictReader(f)
        self.ethusd = []
        for row in reader:
            num_keys = ['price', 'market_cap', 'total_volume']
            for key in num_keys:
                v = row[key]
                if not v:
                    v = 0
                row[key] = float(v)
            self.ethusd.append(row)
        self.ethusd.sort(key=lambda x: x['date'])
        self.users = json.loads(open(user_behavior_filename).read())

    def get_row(self, start_date):
        for row in self.ethusd:
            if row['date'] == start_date:
                return row

    def get_rows(self, start_date, num_days):
        rows = []
        for i, row in enumerate(self.ethusd):
            if row['date'] == start_date:
                return self.ethusd[i:i + num_days]

    def set_max_ltv_from_ema(self, decay_up, decay_down=None):
        if decay_down is None:
            decay_down = decay_up

        n = 365
        window = []

        # for row in self.ethusd:
        #     window.append(row['price'])
        #     if len(window) > n:
        #         window = window[1:]
        #     row['ema'] = sum(window) / len(window)

        ema_ethusd = []
        ema = None
        for row in self.ethusd:
            if ema is None:
                ema = row['price']
            up = row['price'] > ema
            if up:
                ema = ema * (1 - decay_up) + row['price'] * decay_up
            else:
                ema = ema * (1 - decay_down) + row['price'] * decay_down
            row['ema'] = ema


    def funding_rate(self, target_funding_rate, health_factor):
        max_fr = .25
        # max_fr = target_funding_rate * 2
        ltv = 1 / health_factor
        fr = (ltv**5) * .3
        return min(max_fr, fr)

    # in this model:
    # - HF > 1.0 --> yield goes to lenders
    # - HF < 1.0 --> yield goes to lenders at market, funding rate escrowed until price recovers
    def compute_apy(self, start_date, num_days, yield_rate, funding_rate, max_ltv):
        loan_usd = 0
        yield_usd = 0
        pending_funding_eth = 0
        should_refinance = True

        row = self.get_row(start_date)

        # Assume 10 ETH as collateral
        eth = 10

        # Compute its value
        eth_value_usd = eth * row['price']

        # Base the max loan on EMA and an LTV factor
        
        ltv_price_usd = row['ema']
        loan_usd = eth * ltv_price_usd * max_ltv

        real_ltv = loan_usd / eth_value_usd

        rows = self.get_rows(start_date, num_days)
        hf = 1.0
        days_elapsed = 0
        for row in rows:
            value_usd = eth * row['price']
            prev_hf = hf
            hf = value_usd / loan_usd
            fr = self.funding_rate(funding_rate, hf)

            # print('use fr', fr, hf)

            # Yield
            delta_yield = eth * yield_rate * (1/365) * row['price']
            yield_usd += delta_yield

            # Funding if healthy
            if hf > 1.0:
                funding_eth = eth * fr * (1/365)
                delta_funding = funding_eth * row['price']
                yield_usd += delta_funding
                eth -= funding_eth

            # Get new max LTV
            ltv_price_usd = row['ema']

            # Value of our ETH based on the EMA
            eth_ema_value_usd = row['ema'] * eth
            ema_max_usd = row['ema'] * eth * max_ltv

            if ema_max_usd > loan_usd:
                incremental_usd = ema_max_usd - loan_usd
                loan_usd += incremental_usd
            else:
                delta_funding = eth * fr * (1/365) 
                pending_funding_eth += delta_funding

            if prev_hf < 1.0 and hf >= 1.0 and pending_funding_eth > 0:
                # Harvest pending funding
                pending_funding_usd = pending_funding_eth * row['price']
                # print('harvest funding', pending_funding_eth, pending_funding_usd)
                eth -= pending_funding_eth
                yield_usd += pending_funding_usd
                pending_funding_eth = 0

            days_elapsed += 1
            # print('hf', hf)

        # print('yield_usd', yield_usd)

        pending_funding_usd = pending_funding_eth * row['price']

        roi = yield_usd / loan_usd
        apy = roi * (365 / days_elapsed)
        # print('apy %.2f%%' % apy)

        # print('pending_funding_usd', pending_funding_usd)

        return {
            'apy': apy,
            'last_health_factor': hf,
            'pending_funding_eth': pending_funding_eth,
        }
        # return (apy, hf, pending_funding_eth / eth)

    def compute_apy_series(self, start_from, num_days, yield_rate, funding_rate, max_ltv):
        series = []
        for row in self.ethusd:
            if row['date'] < start_from:
                continue

            result = self.compute_apy(
                row['date'],
                num_days,
                yield_rate,
                funding_rate,
                max_ltv)
            
            series.append({
                'price': row['price'],
                'date': row['date'],
                'last_health_factor': result['last_health_factor'],
                'apy': result['apy'],
            })
        return series


def main():
    bt = Backtest('eth_usd.csv', 'aave_users.json')
    bt.set_max_ltv_from_ema(1/100, 1/100)

    result = bt.compute_apy(
        '2018-01-01',
        365,
        0.04,
        0.08,
        0.5)

    print(result)

    # for row in result:
    #     print(row)


if __name__ == '__main__':
    main()
