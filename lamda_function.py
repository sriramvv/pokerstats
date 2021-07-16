import itertools
import re
from typing import List, Set
from collections import defaultdict
from player_stats import WinStats, PlayStats, PreFlopStats, LedgerStats
from db import get_stats_by_date, get_stats_by_month, insert_into_table, update_stats_by_date, update_stats_by_month
from utilities import return_name
from aggregate_stats import compute_aggregates
import urllib.parse
import boto3 as b3
from botocore.exceptions import ClientError


# from variance_stats import hand_variance, flop_variance
class Action:
    def __init__(self, player, action_name, amount):
        self.player = player
        self.action_name = action_name
        self.amount = amount
        # self.time_stamp = time_stamp

    def __str__(self):
        return f"{self.player} {self.action_name} {self.amount}"

    def __repr__(self):
        return self.__str__()


class Player:
    def __init__(self, starting_amount):
        self.stack_amt = starting_amount


class Game:
    def __init__(self, username):
        self.username = username
        self.rounds = []
        self.players = {}
        self.players_ledger = {}
        self.players_away_status = {}

        self.historical_amounts = defaultdict(list)

    def add_away_player(self, name, away_status):
        correct_name = return_name(name)
        self.players_away_status[correct_name] = away_status  # re-join

    def add_player(self, name, amount):
        correct_name = return_name(name)
        if correct_name in self.players:
            if self.players_away_status[correct_name]:
                self.players_away_status[correct_name] = False
            else:
                if amount != 0 and amount != self.players[correct_name]:
                    self.players_ledger[correct_name] += amount  # rebuy
        else:
            self.players[correct_name] = amount
            self.players_ledger[correct_name] = amount
            self.players_away_status[correct_name] = False

    def add_round(self, dealer):
        correct_dealer_name = return_name(dealer)
        if len(self.rounds) != 0:
            self._update_amounts()
        self._record_amounts()
        new_round = Round(correct_dealer_name, self.players, len(self.rounds) + 1)
        self.rounds.append(new_round)
        return new_round

    def _record_amounts(self):
        for player, amt in self.players.items():
            self.historical_amounts[player].append((len(self.rounds), amt))

    def _update_amounts(self):
        last_round = self.rounds[-1]
        spent = last_round.money_spent()
        pot_size = sum(spent.values())
        for user, amount in spent.items():
            self.players[user] -= amount

        if len(last_round.winners) == 1:
            for (winner_name, hand, amt) in last_round.winners:
                self.players[winner_name] += pot_size
        elif len(last_round.winners) > 1:
            for (winner_name, hand, amt) in last_round.winners:
                self.players[winner_name] += amt

    def handle_last_round(self):
        self._update_amounts()
        self._record_amounts()

    def get_rounds(self):
        return [x for x in self.rounds if x.total_money_in_round()]


class Round:
    def __init__(self, dealer, players, number):
        self.initial_amounts = {name: amt for (name, amt) in players.items()}
        self.dealer = dealer
        self.winners = []
        self.number = number  # start numbering from 1

        # Username to hand
        self.known_hands = {}

        self.flop = None
        self.turn = None
        self.river = None

        # Only populated if a round is "run twice"
        self.second_flop = None
        self.second_turn = None
        self.preflop_moves: List[Action] = []
        self.flop_moves: List[Action] = []
        self.turn_moves: List[Action] = []
        self.river_moves: List[Action] = []

    @property
    def small_blind(self) -> (str, int):
        small_blind_action = [x for x in self.preflop_moves if x.action_name == "small_blind"][0]
        return small_blind_action.player, small_blind_action.amount

    @property
    def big_blind(self) -> (str, int):
        big_blind_action = [x for x in self.preflop_moves if x.action_name == "big_blind"][0]
        return big_blind_action.player, big_blind_action.amount

    @staticmethod
    def find_moves(player, action_name, moves):
        return [move for move in moves if (move.player == player and move.action_name == action_name)]

    def add_move(self, player, action_name, amount):
        action = Action(player, action_name, amount)
        if self.flop is None:
            self.preflop_moves.append(action)
        elif self.turn is None:
            self.flop_moves.append(action)
        elif self.river is None:
            self.turn_moves.append(action)
        else:
            self.river_moves.append(action)

    @staticmethod
    def money_in_round(moves):
        """
        How much money was spent by each player in a round
        """
        spent = {}
        for m in moves:
            if m.amount != 0:  # ignore all moves that don't involve money
                if m.action_name == 'uncalled_bet':
                    spent[m.player] -= m.amount
                else:
                    spent[m.player] = m.amount

        for m in moves:
            if m.action_name == "missing_small_blind":
                spent[m.player] += m.amount
            if m.action_name == "missing_big_blind" and not Round.find_moves(m.player, "missing_small_blind", moves):
                spent[m.player] += m.amount

        return spent

    def total_money_in_round(self):
        return sum(self.money_spent().values())

    def money_spent(self):
        spent = defaultdict(int)
        for moves in [self.preflop_moves, self.flop_moves, self.turn_moves, self.river_moves]:
            for player, amount in Round.money_in_round(moves).items():
                spent[player] += amount
        return spent

    def voluntary_contributors(self) -> Set[str]:
        voluntary_contributors = set()
        for m in self.preflop_moves:
            if (
                    m.action_name not in ["small_blind", "big_blind", "missing_big_blind", "missing_small_blind"]
                    and m.amount > 0
            ):
                voluntary_contributors.add(m.player)
        return voluntary_contributors

    def players_present(self) -> Set[str]:
        present = set()
        for m in self.preflop_moves:
            present.add(m.player)
        return present

    def names_in_showdown(self):
        names = set()
        for move in self.river_moves:
            if move.action_name != "fold":
                names.add(move.player)
        return list(names)

    # def __str__(self):
    #     s = f"Round {self.number}\n"
    #     s += f"Game: {self.initial_amounts}\n"
    #     s += f"  {self.preflop_moves}\n"
    #     s += f"  {self.flop_moves}\n"
    #     s += f"  {self.turn_moves}\n"
    #     s += f"  {self.river_moves}\n"
    #     if self.flop is not None:
    #         s += f"  cards -> {' '.join(self.flop)} {self.turn} {self.river}\n"
    #     else:
    #         s += f"  cards -> None\n"
    #     s += f"  winner(s) -> {self.winners}\n"
    #     return s


class Parser:
    def __init__(self, username):
        self.game = Game(username)

    @property
    def _current_round(self):
        return self.game.rounds[-1]

    def parse(self, file_name, username, actual_file) -> Game:
        self.game = Game(username)
        self.username = username
        for line in reversed(actual_file.splitlines()):
            self.parse_line(line)
        self.game.handle_last_round()
        game = self.game
        self.game = None
        return game

    def parse_line(self, line):
        # row, time, token = line
        line = line.replace('.', '').lower()
        if "joined the game with a stack of" in line:  # or "the admin approved" in line:
            player_name = re.findall(r'"([^"]*)"', line)[1].split("@")[0].strip()
            start_amount = int(re.search(r'with a stack of (\d+)', line).group(1))
            self.game.add_player(player_name, start_amount)
        elif "-- starting hand" in line:
            if "dead button" in line:
                dealer_name = "None"
            else:
                dealer_name = re.findall(r'"([^"]*)"', line)[1].split("@")[0].strip()
                # print(re.findall(r'"([^"]*)"', line)[1].split("@")[0].strip())
            # print(f"Started hand dealer: {dealer_name}")
            self.game.add_round(dealer_name)
        elif "player stacks:" in line:
            line = line[len("Player stacks: "):]
            entries = line.split(",")
            entries = entries[0].split(" | ")
            stack_sizes = [x.strip().rsplit(' ', 1)[1] for x in entries]
            # stack_size_counts = [int(x.strip('()')) for x in stack_sizes]
            stack_size_counts = [int(re.search(r'\d+', x).group()) for x in stack_sizes]
            players = [return_name(x.split('"')[2].split("@")[0].strip()) for x in entries]
            # for x in entries:
            #     print(x.split('"')[2].split("@")[0].strip())
            player_amounts = {player: stack_size for (player, stack_size) in zip(players, stack_size_counts)}
            for player, amount in player_amounts.items():
                if amount != self.game.players[player]:
                    round_no = self._current_round.number
                    # print(f"**WARNING** start of round #{round_no}: "
                    #       f"{player}: {amount} (amount from log) != {self.game.players[player]} (our amount)")
                    if len(self.game.rounds) > 1:
                        pass
                        # print("winners in prev round: ", self.game.rounds[-2].winners)
                    self.game.players[player] = amount
        elif "posts a small blind of" in line:
            player_name = return_name(re.findall(r'"([^"]*)"', line)[1].split("@")[0].strip())
            small_blind = int(re.search(r'small blind of (\d+)', line).group(1))
            self._current_round.add_move(player_name, "small_blind", small_blind)
        elif re.search(r'"(.*)" posts a big blind of (\d+)', line):
            match = re.search(r'"(.*)" posts a big blind of (\d+)', line)
            player_name = return_name(match.group(1).split("@")[0].strip('" '))
            big_blind = int(match.group(2))
            self._current_round.add_move(player_name, "big_blind", big_blind)
        elif "folds" in line:
            player_name = return_name(re.findall(r'"([^"]*)"', line)[1].split("@")[0].strip())
            self._current_round.add_move(player_name, "fold", 0)
        elif "checks" in line:
            player_name = return_name(re.findall(r'"([^"]*)"', line)[1].split("@")[0].strip())
            self._current_round.add_move(player_name, "check", 0)
        elif re.search(r'"(.*)" calls (\d+) and go all', line):
            match = re.search(r'"(.*)" calls (\d+) and go all', line)
            player_name = return_name(match.group(1).split("@")[0].strip('" '))
            call_amount = int(match.group(2))
            self._current_round.add_move(player_name, "call (all in)", call_amount)
        elif re.search(r'"(.*)" calls (\d+)', line):
            match = re.search(r'"(.*)" calls (\d+)', line)
            player_name = return_name(match.group(1).split("@")[0].strip('" '))
            call_amount = int(match.group(2))
            self._current_round.add_move(player_name, "call", call_amount)
        elif re.search(r'"(.*)" raises to (\d+) and go all', line):
            match = re.search(r'"(.*)" raises to (\d+) and go all', line)
            player_name = return_name(match.group(1).split("@")[0].strip('" '))
            raise_amount = int(match.group(2))
            self._current_round.add_move(player_name, "raise (all in)", raise_amount)
        elif re.search(r'"(.*)" raises to (\d+)', line):
            match = re.search(r'"(.*)" raises to (\d+)', line)
            player_name = return_name(match.group(1).split("@")[0].strip('" '))
            raise_amount = int(match.group(2))
            self._current_round.add_move(player_name, "raise", raise_amount)
        elif re.search(r'"(.*)" bets (\d+) and go all', line):
            # TODO: This is the first bet in a round, should be treated differently
            match = re.search(r'"(.*)" bets (\d+) and go all', line)
            player_name = return_name(match.group(1).split("@")[0].strip('" '))
            raise_amount = int(match.group(2))
            self._current_round.add_move(player_name, "raise (all in)", raise_amount)
        elif re.search(r'"(.*)" bets (\d+)', line):
            # TODO: This is the first bet in a round, should be treated differently
            match = re.search(r'"(.*)" bets (\d+)', line)
            player_name = return_name(match.group(1).split("@")[0].strip('" '))
            raise_amount = int(match.group(2))
            self._current_round.add_move(player_name, "raise", raise_amount)
        elif "uncalled bet" in line:
            for amount, player_name in re.findall(r'uncalled bet of (\d+) returned to "(.*)"', line):
                self._current_round.add_move(return_name(player_name.split("@")[0].strip('" ')), "uncalled_bet",
                                             int(amount))
                break
        elif re.search(r'"(.*)" collected (\d+) from pot with .* \(combination: (.*)\)', line):
            match = re.search(r'"(.*)" collected (\d+) from pot with .* \(combination: (.*)\)', line)
            winner_name = return_name(match.group(1).split("@")[0].strip('" '))
            win_amount = int(match.group(2))
            combination = match.group(3)
            winning_hand = combination.split(", ")
            self._current_round.known_hands[winner_name] = winning_hand
            self._current_round.winners.append((winner_name, winning_hand, win_amount))
        elif re.search(r'"(.*)" collected (\d+) from pot', line):
            match = re.search(r'"(.*)" collected (\d+) from pot', line)
            winner_name = return_name(match.group(1).split("@")[0].strip('" '))
            win_amount = int(match.group(2))
            self._current_round.winners.append((winner_name, None, win_amount))
        elif "dead small blind" in line or "dead big blind" in line:
            pass
        elif "requested a seat" in line:
            pass
        elif "canceled the seat request" in line:
            pass
        elif "rejected the seat request" in line:
            pass
        elif "changed the id from" in line:
            pass
        elif "stand up with the stack" in line:
            player_name = re.findall(r'"([^"]*)"', line)[1].split("@")[0].strip()
            self.game.add_away_player(player_name, True)
        elif "sit back with the stack" in line:
            pass
        elif "quits the game with a stack of" in line:
            pass
        elif "joined the game with a stack of" in line:
            pass
        elif "passed the room ownership" in line:
            pass
        elif "queued the stack change for the player" in line:
            pass
        elif "enqueued the removal of the player " in line:
            pass
        elif "updated the player" in line:
            pass
        elif "small blind was changed from" in line:
            pass
        elif "big blind was changed from" in line:
            pass
        elif "flop:" in line:
            card_string = line.split('[')[1].split(']')[0]
            cards = card_string.split(', ')
            self._current_round.flop = cards
        elif "turn:" in line:
            card = line.split('[')[1].split(']')[0]
            self._current_round.turn = card
        elif "river:" in line:
            card = line.split('[')[1].split(']')[0]
            self._current_round.river = card
        elif "-- ending hand" in line:
            pass
            # print(self._current_round)
            # self._current_round = None
        elif " shows a " in line:
            player_name = return_name(re.findall(r'"([^"]*)"', line)[1].split("@")[0].strip())
            # assert line.endswith('.')
            line = line.replace('"', '')
            cards = line.split(" shows a ")[1].split(",")[:-2]
            self._current_round.known_hands[player_name] = cards
            self._current_round.add_move(player_name, "show", 0)
        else:
            pass
            # print("**WARNING**: Unexpected line found in log. "
            #       "Likely the log format has changed and this script needs to be updated.")
            # print(line)


def merge_dict_list(shared_key, *iterables):
    result = defaultdict(dict)
    for dictionary in itertools.chain.from_iterable(iterables):
        result[dictionary[shared_key]].update(dictionary)
    for dictionary in result.values():
        dictionary.pop(shared_key)
    return result


def compute_stats(game, file_dt):
    win_stats = WinStats(game)
    play_stats = PlayStats(game, win_stats)
    preflop_stats = PreFlopStats(game, play_stats)
    ledger_stats = LedgerStats(game)
    # flop_variance(game)

    ps_data = play_stats.as_dict()
    ws_data = win_stats.as_dict()
    pf_data = preflop_stats.as_dict()
    ls_data = ledger_stats.as_dict()
    merged_dict = merge_dict_list('Player', ps_data, ws_data, pf_data, ls_data)
    merged_data = {}
    file_dt = "/".join(file_dt)

    for key, value in merged_dict.items():
        data = {
            "Player": key,
            "Date_Played": file_dt
            }
        merged_data.update(data)
        for k, v in value.items():
            v = v.replace(" ", "")
            data = {f"{k}": f"{v}"}
            merged_data.update(data)
        merge_response = update_stats_by_date(merged_data, None)


def lambda_handler(event, context):
    # Get the object from the event and show its content type
    s3 = b3.client('s3','us-east-1') 
    # bucket_name = 'pokernowlogsbucket'
    bucket = event['Records'][0]['s3']['bucket']['name']
    print(bucket)
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')
    print(key)
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        print("CONTENT TYPE: " + response['ContentType'])
        p = Parser("")
        file_dt = re.findall(r'\d+', key)
        contents=response['Body'].read().decode(encoding="utf-8",errors="ignore")
        game = p.parse(key, '', contents)
        compute_stats(game, file_dt)
        #compute_aggregates(file_dt)
    except Exception as e:
        print(e)
        print('Error getting object {} from bucket {}. Make sure they exist and your bucket is in the same region as this function.'.format(key, bucket))
        raise e