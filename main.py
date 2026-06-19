import os
import sys
from collections import defaultdict

from cg.api import AreaType, CardType, Log, LogType, Observation, SelectContext, OptionType, Card, Pokemon, State, all_card_data, to_observation_class

"""
Ceruledge ex (ソウブレイズex) Deck
"""

# Load deck.csv
file_path = "deck.csv"
if not os.path.exists(file_path):
    file_path = "/kaggle_simulations/agent/" + file_path
with open(file_path, "r") as file:
    csv = file.read().split("\n")
my_deck = []
for i in range(60):
    my_deck.append(int(csv[i]))

# Load all card data
all_card = all_card_data()
card_table = {c.cardId: c for c in all_card}

# === Card ID Constants ===
Charcadet = 796
Ceruledge_ex = 320
Budew = 235
Fezandipiti_ex = 140
Ultra_Ball = 1121
Buddy_Buddy_Poffin = 1086
Crushing_Hammer = 1120
Night_Stretcher = 1097
Switch = 1123
Unfair_Stamp = 1080
Zeyu = 1192
Lillie_Determination = 1227
Boss_Orders = 1182
Aoki_Tegiwa = 1206
Battle_Colosseum = 1264
Basic_Fire_Energy = 2

UNNECESSARY = -10000000

# === Global State ===
_can_switch = False
_can_attack = False
_can_main_attack = False
_use_support = 0
_bench_attacker = False
_pre_turn_log = []
_current_turn_log = []
_prize = []
_card_counts = defaultdict(int)
_serial_set = set()


def agent(obs_dict):
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return my_deck

    global _can_switch, _can_attack, _can_main_attack, _use_support, _bench_attacker
    global _pre_turn_log, _current_turn_log

    state = obs.current
    select = obs.select
    context = select.context
    my_index = state.yourIndex
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]

    # --- Helper functions (inside agent to avoid Kaggle picking them up) ---

    def prize_count(pokemon, is_attack_damage):
        data = card_table[pokemon.id]
        count = 3 if data.megaEx else 2 if data.ex else 1
        if is_attack_damage:
            for card in pokemon.energyCards:
                if card.id == 12:
                    count -= 1
            for card in pokemon.tools:
                if card.id == 1172 and "Lillie" in data.name:
                    count -= 1
        return max(0, count)

    def pokemon_score(pokemon, is_attack_damage):
        data = card_table[pokemon.id]
        score = prize_count(pokemon, is_attack_damage) * 1000
        score += len(pokemon.energies) * 150
        score += len(pokemon.tools) * 100
        if data.stage2:
            score += 250
        elif data.stage1:
            score += 130
        score += pokemon.hp
        return score

    def calc_damage(discard_energy_count):
        return 30 + 20 * discard_energy_count

    def add_card_count(card, mi):
        if card is None:
            return
        if isinstance(card, Pokemon) or card.playerIndex == mi:
            if card.serial not in _serial_set:
                _card_counts[card.id] -= 1
                _serial_set.add(card.serial)
        if isinstance(card, Pokemon):
            for c in card.energyCards:
                add_card_count(c, mi)
            for c in card.tools:
                add_card_count(c, mi)
            for c in card.preEvolution:
                add_card_count(c, mi)

    def set_card_counts():
        _card_counts.clear()
        _serial_set.clear()
        for cid in my_deck:
            _card_counts[cid] += 1
        for card in my_state.hand:
            add_card_count(card, my_index)
        for card in my_state.discard:
            add_card_count(card, my_index)
        for card in my_state.bench:
            add_card_count(card, my_index)
        for card in my_state.active:
            add_card_count(card, my_index)
        for card in state.stadium:
            add_card_count(card, my_index)
        if state.looking is not None:
            for card in state.looking:
                add_card_count(card, my_index)
        add_card_count(select.effect, my_index)

    def get_card(area, index, player_index):
        ps = state.players[player_index]
        if area == AreaType.DECK:
            return select.deck[index]
        elif area == AreaType.HAND:
            return ps.hand[index]
        elif area == AreaType.DISCARD:
            return ps.discard[index]
        elif area == AreaType.ACTIVE:
            return ps.active[index]
        elif area == AreaType.BENCH:
            return ps.bench[index]
        elif area == AreaType.PRIZE:
            return ps.prize[index]
        elif area == AreaType.STADIUM:
            return state.stadium[index]
        elif area == AreaType.LOOKING:
            return state.looking[index]
        return None

    def hand_score_eval(cid, ignore_count):
        score = 0
        if cid == Charcadet:
            score = 18000 if main_pokemon_count < 3 else 1000
        elif cid == Ceruledge_ex:
            if can_evolve_charcadet:
                if field_counts[Ceruledge_ex] == 0:
                    score = 40000
                elif field_counts[Ceruledge_ex] == 1:
                    score = 15000
                else:
                    score = 50
            else:
                score = 3000
        elif cid == Budew:
            if field_counts[Budew] >= 1 or state.turn >= 3:
                score = UNNECESSARY
            elif state.turn <= 2:
                score = 25000
            else:
                score = 100
        elif cid == Fezandipiti_ex:
            score = 50000 if pre_ko else 5
        elif cid == Unfair_Stamp:
            if pre_ko:
                score = 80000
            elif len(op_state.prize) <= 2:
                score = UNNECESSARY
            else:
                score = 80
        elif cid == Buddy_Buddy_Poffin:
            if deck_counts[Charcadet] > 0:
                score = 35000
            elif state.turn <= 2 and deck_counts[Budew] > 0:
                score = 30000
            else:
                score = UNNECESSARY
        elif cid == Ultra_Ball:
            score = 70 if (main_pokemon_count <= 2 or field_counts[Charcadet] >= 1) else 5
        elif cid == Night_Stretcher:
            if discard_counts[Ceruledge_ex] >= 1 and field_counts[Ceruledge_ex] == 0:
                score = 30000
            elif discard_counts[Charcadet] >= 1 and main_pokemon_count <= 1:
                score = 25000
            else:
                score = 50
        elif cid == Crushing_Hammer:
            score = 20
        elif cid == Switch:
            score = 15
        elif cid == Boss_Orders:
            score = 60000
        elif cid == Zeyu:
            score = 45000 if (ignore_count or support_count == 0) else 10
        elif cid == Aoki_Tegiwa:
            score = 40000 if (ignore_count or support_count == 0) else 10
        elif cid == Lillie_Determination:
            score = 35000 if (ignore_count or support_count == 0) else 10
        elif cid == Battle_Colosseum:
            score = 4000 if (stadium_id != 0 and stadium_id != Battle_Colosseum) else 100
        elif cid == Basic_Fire_Energy:
            score = 10000
        if not ignore_count and hand_counts.get(cid, 0) > 0:
            if cid == Charcadet:
                score -= 100
            elif cid == Basic_Fire_Energy:
                score -= 50
            else:
                score -= 100000
        return score

    def attach_score_eval(attach_id, pokemon, active):
        energy_count = len(pokemon.energies)
        if card_table[attach_id].cardType == CardType.TOOL:
            return 60000 + (1000 if active else 0)
        if pokemon.id == Budew or pokemon.id == Fezandipiti_ex:
            return -1
        if pokemon.id == Ceruledge_ex:
            if energy_count == 0:
                return 25000 + (5000 if active else 0)
            else:
                return -1
        if pokemon.id == Charcadet:
            if energy_count == 0 and active and not _bench_attacker:
                return 18000
            else:
                return -1
        return -1

    # --- Log tracking ---
    if state.turn == 0:
        _prize.clear()
        _pre_turn_log = []
        _current_turn_log = []
    else:
        for log in obs.logs:
            _current_turn_log.append(log)
            if log.type == LogType.TURN_END:
                _pre_turn_log = _current_turn_log
                _current_turn_log = []

    pre_ko = False
    no_item = False
    for log in _pre_turn_log:
        if log.type == LogType.ATTACK:
            if log.attackId == 323:
                no_item = True
        elif log.type == LogType.MOVE_CARD:
            if (log.playerIndex == my_index
                and (log.fromArea == AreaType.BENCH or log.fromArea == AreaType.ACTIVE)
                and log.toArea == AreaType.DISCARD):
                pre_ko = True

    # --- Track deck contents ---
    if select.deck is not None:
        set_card_counts()
        for card in select.deck:
            _card_counts[card.id] -= 1
        _prize.clear()
        for cid in _card_counts:
            for _ in range(_card_counts[cid]):
                _prize.append(cid)

    set_card_counts()
    for cid in _prize:
        _card_counts[cid] -= 1
    deck_counts = _card_counts

    # --- Count cards on field / hand / discard ---
    field_counts = defaultdict(int)
    hand_counts = defaultdict(int)
    discard_counts = defaultdict(int)
    discard_energy_count = 0

    active_id = 0
    can_evolve_charcadet = False
    _bench_attacker = False

    for card in my_state.active:
        if card is None:
            continue
        active_id = card.id
        field_counts[card.id] += 1
        if not card.appearThisTurn and card.id == Charcadet:
            can_evolve_charcadet = True
    for card in my_state.bench:
        field_counts[card.id] += 1
        if not card.appearThisTurn and card.id == Charcadet:
            can_evolve_charcadet = True
        if card.id == Ceruledge_ex and len(card.energies) >= 1:
            _bench_attacker = True

    for card in my_state.hand:
        hand_counts[card.id] += 1

    for card in my_state.discard:
        discard_counts[card.id] += 1
        if card_table[card.id].cardType == CardType.BASIC_ENERGY:
            discard_energy_count += 1

    main_pokemon_count = field_counts[Charcadet] + field_counts[Ceruledge_ex]
    current_damage = calc_damage(discard_energy_count)

    stadium_id = 0
    for card in state.stadium:
        stadium_id = card.id

    support_count = 0
    for card in my_state.hand:
        if card_table[card.id].cardType == CardType.SUPPORTER and card.id != Boss_Orders:
            support_count += 1

    # --- Determine available actions in MAIN context ---
    _can_switch = False
    _can_attack = False
    _can_main_attack = False
    if context == SelectContext.MAIN:
        for o in select.option:
            if o.type == OptionType.RETREAT:
                _can_switch = True
            elif o.type == OptionType.ATTACK:
                _can_attack = True
                if active_id == Ceruledge_ex:
                    _can_main_attack = True

        _use_support = 0
        if not state.supporterPlayed:
            sup_score = 0
            for o in select.option:
                if o.type == OptionType.PLAY:
                    card = get_card(AreaType.HAND, o.index, my_index)
                    if card_table[card.id].cardType == CardType.SUPPORTER:
                        sc = hand_score_eval(card.id, True)
                        if sup_score < sc:
                            sup_score = sc
                            _use_support = card.id

    # スボミーがバトル場にいる間はグッズロックを続けるため入れ替えない
    if active_id == Budew:
        do_switch = False
    else:
        do_switch = (not _can_main_attack
                     and active_id != Ceruledge_ex
                     and _bench_attacker)

    # --- Score each option ---
    scores = []
    for o in select.option:
        score = 0

        if o.type == OptionType.NUMBER:
            score = o.number

        elif o.type == OptionType.YES:
            score = 1

        elif o.type == OptionType.CARD:
            card = get_card(o.area, o.index, o.playerIndex)
            if card is not None:
                energy_count = 0
                hp = 0
                if isinstance(card, Pokemon):
                    energy_count = len(card.energies)
                    hp = card.hp

                if (context == SelectContext.SWITCH
                    or context == SelectContext.TO_ACTIVE
                    or context == SelectContext.SETUP_ACTIVE_POKEMON):
                    if o.playerIndex == my_index:
                        if card.id == Ceruledge_ex:
                            score += 50000 + energy_count * 5000
                        elif card.id == Charcadet:
                            score += 10000
                        elif card.id == Budew:
                            if context == SelectContext.SETUP_ACTIVE_POKEMON:
                                score += 100000 if my_index != state.firstPlayer else 5000
                            elif not _bench_attacker:
                                score += 30000
                            else:
                                score += 3000
                        elif card.id == Fezandipiti_ex:
                            score += 1000
                        score += energy_count * 1000 + hp
                    else:
                        score += pokemon_score(card, True)
                        if hp <= current_damage:
                            score += 50000

                elif context == SelectContext.SETUP_BENCH_POKEMON:
                    score = 10000 if card.id == Charcadet else -1

                elif context == SelectContext.TO_BENCH:
                    if card.id == Charcadet:
                        score = 20000 if main_pokemon_count < 3 else 5000
                    elif card.id == Budew:
                        score = 18000 if (field_counts[Budew] == 0 and state.turn <= 2) else -1
                    else:
                        score = 1000

                elif context == SelectContext.TO_HAND:
                    score = hand_score_eval(card.id, False)
                    hand_counts[card.id] += 1

                elif context == SelectContext.DISCARD:
                    hand_counts[card.id] -= 1
                    if card_table[card.id].cardType == CardType.SUPPORTER:
                        support_count -= 1
                    # ポケモンとACE SPECは絶対に捨てない
                    card_data = card_table[card.id]
                    if card_data.cardType == CardType.POKEMON:
                        score = -200000
                    elif card.id == Unfair_Stamp or card.id == Crushing_Hammer:
                        score = -200000
                    elif card.id == Basic_Fire_Energy:
                        # このエネを捨てたら相手バトル場を倒せるか判定
                        op_active_hp = 0
                        if op_state.active and op_state.active[0] is not None:
                            op_active_hp = op_state.active[0].hp
                        damage_if_discard = calc_damage(discard_energy_count + 1)
                        can_ko_if_discard = (op_active_hp > 0 and damage_if_discard >= op_active_hp
                                             and current_damage < op_active_hp)

                        if can_ko_if_discard:
                            # 捨てれば倒せる → サイドを進めることを最優先
                            score = 100000
                        else:
                            # ベンチにエネ付きソウブレイズexがいれば予備アタッカーがいるので全部捨ててOK
                            has_bench_backup = any(
                                bc.id == Ceruledge_ex and len(bc.energies) >= 1
                                for bc in my_state.bench
                            )
                            if has_bench_backup:
                                score = 100000
                            elif not state.energyAttached and hand_counts.get(Basic_Fire_Energy, 0) <= 0:
                                # 予備アタッカーなし＆まだ手貼りしていない＆最後の1枚 → 残す
                                score = -50000
                            else:
                                score = 100000
                    else:
                        score = -hand_score_eval(card.id, False)

                elif context == SelectContext.DAMAGE_COUNTER or context == SelectContext.DAMAGE_COUNTER_ANY:
                    if hp > 0:
                        score = 100000 - 10 * hp + pokemon_score(card, False)
                        if hp <= 10:
                            score += 50000

                elif context == SelectContext.ATTACH_FROM:
                    if card.id == Ceruledge_ex:
                        score = 30000 + (5000 if o.area == AreaType.ACTIVE else 0)
                    elif card.id == Charcadet:
                        score = 15000
                    else:
                        score = 5000

        elif o.type == OptionType.ENERGY_CARD or o.type == OptionType.ENERGY:
            if o.playerIndex != my_index:
                score = 20 if o.area == AreaType.ACTIVE else 10
                card = get_card(o.area, o.index, o.playerIndex)
                if card_table[card.id].cardType == CardType.SPECIAL_ENERGY:
                    score += 5
            else:
                score = 1

        elif o.type == OptionType.PLAY:
            card = get_card(AreaType.HAND, o.index, my_index)

            if card.id == Charcadet:
                score = 51000 if main_pokemon_count < 3 else 20000
            elif card.id == Budew:
                score = 52000 if (field_counts[Budew] == 0 and state.turn <= 2) else -1
            elif card.id == Fezandipiti_ex:
                score = 53000 if pre_ko else -1
            elif card.id == Unfair_Stamp:
                if pre_ko:
                    score = 80000
                elif len(op_state.prize) <= 2:
                    score = UNNECESSARY
                else:
                    score = 80
            elif card.id == Buddy_Buddy_Poffin:
                score = 46000 if (deck_counts[Charcadet] > 0 or (state.turn <= 2 and deck_counts[Budew] > 0)) else -1
            elif card.id == Ultra_Ball:
                if hand_counts[Basic_Fire_Energy] >= 2:
                    score = 48000
                elif hand_counts[Basic_Fire_Energy] >= 1:
                    score = 44000
                elif main_pokemon_count <= 2:
                    score = 42000
                else:
                    score = 30
            elif card.id == Night_Stretcher:
                if discard_counts[Ceruledge_ex] >= 1 and field_counts[Ceruledge_ex] == 0:
                    score = 42000
                elif discard_counts[Charcadet] >= 1 and main_pokemon_count <= 1:
                    score = 42000
                else:
                    score = -1
            elif card.id == Crushing_Hammer:
                score = 40000
            elif card.id == Switch:
                score = 38000 if do_switch else -1
            elif card.id == Battle_Colosseum:
                if stadium_id > 0 and stadium_id != Battle_Colosseum:
                    score = 80000
                elif stadium_id == 0:
                    score = 36000
                else:
                    score = -1
            elif card.id == Zeyu:
                score = 35000 if card.id == _use_support else -1
            elif card.id == Aoki_Tegiwa:
                score = 35000 if card.id == _use_support else -1
            elif card.id == Lillie_Determination:
                score = 14000 if card.id == _use_support else -1
            elif card.id == Boss_Orders:
                score = 35000 if card.id == _use_support else -1

        elif o.type == OptionType.ATTACH:
            card = get_card(o.area, o.index, my_index)
            pokemon = get_card(o.inPlayArea, o.inPlayIndex, my_index)
            score = attach_score_eval(card.id, pokemon, o.inPlayArea == AreaType.ACTIVE)

        elif o.type == OptionType.EVOLVE:
            pokemon = get_card(o.inPlayArea, o.inPlayIndex, my_index)
            score = (70000 + len(pokemon.energies)) if pokemon.id == Charcadet else -1

        elif o.type == OptionType.ABILITY:
            card = get_card(o.area, o.index, my_index)
            score = 1 if card.id == 1267 else 40000

        elif o.type == OptionType.RETREAT:
            score = 10000 if do_switch else -1

        elif o.type == OptionType.ATTACK:
            score = o.attackId if o.attackId > 0 else 1

        scores.append(score)

    # --- Build output ---
    output = []
    if len(scores) >= 1:
        sorted_scores = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        for i in range(select.maxCount):
            if i >= len(sorted_scores):
                break
            if (sorted_scores[i][1] >= 0
                or select.minCount > i
                or (context != SelectContext.TO_BENCH and context != SelectContext.SETUP_BENCH_POKEMON)):
                output.append(sorted_scores[i][0])

    # Safety: always return at least minCount items
    if len(output) < select.minCount:
        sorted_scores = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        for idx, _ in sorted_scores:
            if idx not in output:
                output.append(idx)
            if len(output) >= select.minCount:
                break

    return output
