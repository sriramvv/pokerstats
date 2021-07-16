from collections import defaultdict
from utilities import avg, safe_div, median


class LedgerStats:
    def __init__(self, evening):
        self.evening = evening
        # buyin = defaultdict(list)
        # buyout = defaultdict(list)

    def as_dict(self):
        # Define dictionary containing the players
        # buyin = self.buyin
        # buyout = self.buyout
        ledgerstats_data = []

        for player in self.evening.players.keys():
            earning = self.evening.players[player] - self.evening.players_ledger[player]
            buyin = safe_div(self.evening.players_ledger[player], 100)
            buyout = safe_div(self.evening.players[player], 100)
            profit_loss = safe_div(earning, 100)
            profit_percentage = safe_div(profit_loss, buyin) * 100
            # Populate dictionary containing the players
            data = {'Player': player, 'BuyIn': f"{buyin:>3.0f}",
                    'BuyOut': f"{buyout:>6.2f}",
                    'Profit_Loss': f"{profit_loss:>6.2f}",
                    'Profit_Loss_Percentage': f"{profit_percentage:>6.2f}%",
                    }

            # Convert dictionary to dataframe
            ledgerstats_data.append(data)

        return ledgerstats_data


class WinStats:
    def __init__(self, evening):
        # # of wins
        # avg size of wins
        self.evening = evening
        wins = defaultdict(list)
        showdown_wins = defaultdict(list)
        preshowdown_wins = defaultdict(list)
        for round in evening.get_rounds():
            for (player, hand, amt) in round.winners:
                wins[player].append(amt)
                if hand is None:
                    preshowdown_wins[player].append(amt)
                else:
                    showdown_wins[player].append(amt)
        self.wins = wins
        self.showdown_wins = showdown_wins
        self.preshowdown_wins = preshowdown_wins

    def as_dict(self):
        showdown_wins = self.showdown_wins
        preshowdown_wins = self.preshowdown_wins
        # # Define list containing the players
        winstats_data = []

        for player in self.evening.players.keys():
            num_wins = len(showdown_wins[player]) + len(preshowdown_wins[player])
            pct_at_showdown = safe_div(len(showdown_wins[player]),  num_wins) * 100
            pct_at_preshowdown = safe_div(len(preshowdown_wins[player]), num_wins) * 100
            win_amts = showdown_wins[player] + preshowdown_wins[player]

            median_win_amt = median(win_amts)
            median_showdown_amt = median(showdown_wins[player])
            median_preshowdown_amt = median(preshowdown_wins[player])

            # Populate dictionary containing the players
            data = {'Player': player, 'Rounds_Won': f"{num_wins:>2}",
                    'Median_Win_Amt': f"{median_win_amt :0.0f}",
                    'Showdown_Win_Percentage': f"{pct_at_showdown:>6.2f}%",
                    'Median_Showdown_Amt': f"{median_showdown_amt :0.0f}",
                    'Pre_Showdown_Win_Percentage': f"{pct_at_preshowdown:>6.2f}%",
                    'Median_Preshowdown_Amt': f"{median_preshowdown_amt:0.0f}"
                    }
            winstats_data.append(data)

        return winstats_data


class PlayStats:
    def __init__(self, evening, win_stats: WinStats):
        self.evening = evening
        self.win_stats = win_stats
        rounds_present = defaultdict(int)
        rounds_contributed = defaultdict(int)
        showdowns_played = defaultdict(int)
        for round in evening.get_rounds():
            for player in round.names_in_showdown():
                showdowns_played[player] += 1

            for player in round.voluntary_contributors():
                rounds_contributed[player] += 1

            for player in round.players_present():
                rounds_present[player] += 1

        self.rounds_present = rounds_present
        self.rounds_contributed = rounds_contributed
        self.showdowns_played = showdowns_played

    def as_dict(self):
        # % How often you saw each stage
        # % Showdowns won
        # date_time = datetime.now().strftime("%m/%d/%Y")
        # Define dictionary containing the players
        playstats_data = []

        max_rounds = len(self.evening.get_rounds())
        print(f"Rounds: {max_rounds}")
        for player in self.evening.players.keys():
            total_rounds = self.rounds_present[player]
            player_wins = len(self.win_stats.wins[player])
            player_showdown_wins = len(self.win_stats.showdown_wins[player])
            pct_played = safe_div(self.rounds_contributed[player], total_rounds) * 100
            pct_played_wins = safe_div(player_wins, self.rounds_contributed[player]) * 100
            pct_showdown_wins = safe_div(player_showdown_wins, self.showdowns_played[player]) * 100

            data = {'Player': player,
                    # 'Date_Played': file_dt,
                    'Rounds_Won': f"{player_wins:>3d}",
                    'Rounds_Played': f"{self.rounds_contributed[player]:>3d}",
                    'Total_Rounds': f"{total_rounds:>3d}",
                    'Showdowns_Won': f"{player_showdown_wins:>3d}",
                    'Showdowns_Faced': f"{self.showdowns_played[player]:>3d}",
                    'VPIP_Percentage':  f"{pct_played:>6.2f}%",
                    'Win_Percentage': f"{pct_played_wins:>6.2f}%"
                    }
            playstats_data.append(data)

        return playstats_data


class PreFlopStats:
    def __init__(self, evening, play_stats: PlayStats):
        # How many times did you limp
        # How many times did you call, what was your avg call
        # How many times did you raise, what was your avg raise
        self.evening = evening
        self.play_stats = play_stats
        limp_rounds = defaultdict(list)
        raise_amts = defaultdict(list)
        raise_rounds = defaultdict(list)
        three_bet_amts = defaultdict(list)
        three_bet_rounds = defaultdict(list)

        for round in evening.get_rounds():
            preflop_amounts = round.money_in_round(round.preflop_moves)
            for player, amt in preflop_amounts.items():
                if amt == round.big_blind[1] and 0 == len(round.find_moves(player, "fold", round.preflop_moves)):
                    limp_rounds[player].append(round)

            # In case there are multiple raises in a single round
            round_raises = {}
            round_3bets = {}
            open_raise = False
            three_bet = False
            for move in round.preflop_moves:
                if move.action_name == "raise":
                    round_raises[move.player] = move.amount
                    if not open_raise:
                        open_raise = True
                    elif not three_bet:
                        round_3bets[move.player] = move.amount
                        three_bet = True

            for player, amt in round_raises.items():
                raise_amts[player].append(amt)
                raise_rounds[player].append(round)

            for player, amt in round_3bets.items():
                three_bet_amts[player].append(amt)
                three_bet_rounds[player].append(round)

        self.limp_rounds = limp_rounds
        self.raise_amts = raise_amts
        self.raise_rounds = raise_rounds
        self.three_bet_amts = three_bet_amts
        self.three_bet_rounds = three_bet_rounds

    def as_dict(self):
        # Define dictionary containing the players
        playstats_data = []

        for player in self.evening.players.keys():
            total_rounds = self.play_stats.rounds_present[player]
            pct_played = safe_div(self.play_stats.rounds_contributed[player], total_rounds) * 100
            pct_limped = safe_div(len(self.limp_rounds[player]), self.play_stats.rounds_contributed[player]) * 100
            pct_raised = safe_div(len(self.raise_rounds[player]), total_rounds) * 100
            pct_3bet = safe_div(len(self.three_bet_rounds[player]), total_rounds) * 100

            data = {'Player': player, 'Avg_Raise_Amount': f"{avg(self.raise_amts[player]):>3.0f}",
                    'Avg_3_Bet_Amount': f"{avg(self.three_bet_amts[player]):>3.0f}",
                    # 'Num. Voluntary / Rounds Played (VPIP)': f"{self.play_stats.rounds_contributed[player]:>3d} / {total_rounds:>3d} ({pct_played:>6.2f}%)",
                    'Rounds_Raised': f"{len(self.raise_rounds[player]):>3d}",
                    'PFR_Percentage': f"{pct_raised:>6.2f}%",
                    # 'Rounds 3-Bet / Rounds Present (3BET)': f"{len(self.three_bet_rounds[player]):>3d} / {self.play_stats.rounds_present[player]:>3d} ({pct_3bet:>6.2f}%)",
                    'Rounds_Limped': f"{len(self.limp_rounds[player]):>3d}",
                    'Limped_Percentage': f"{pct_limped:>6.2f}%"
                    }

            playstats_data.append(data)

        return playstats_data


def fold_stats():
    # What amount causes a person to fold (absolute) vs (relative to pot)
    pass
