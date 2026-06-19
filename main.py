import os
import sys
from collections import defaultdict

from cg.api import AreaType, CardType, Log, LogType, Observation, SelectContext, OptionType, Card, Pokemon, State, all_card_data, to_observation_class

"""
Ceruledge ex (ソウブレイズex) Deck - v3
モグリュー + 闘エネルギー + パーフェクトミキサーによるトラッシュ加速型
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
Mogurew = 81
Budew = 235
Fezandipiti_ex = 140
Ultra_Ball = 1121
Buddy_Buddy_Poffin = 1086
Poke_Pad = 1152
Fight_Gong = 1142
Night_Stretcher = 1097
Switch = 1123
Perfect_Mixer = 1128
Zeyu = 1192
Lillie_Determination = 1227
Boss_Orders = 1182
Ogerpon_Hearth = 358
Ishizumai_A = 344
Ishizumai_B = 532
Iwaparesu = 345
Basic_Grass_Energy = 1
Basic_Fire_Energy = 2
Basic_Fighting_Energy = 6

UNNECESSARY = -10000000

# === Global State ===
_pre_turn_log = []
_current_turn_log = []
_prize = []
_card_counts = defaultdict(int)
_serial_set = set()
_iwaparesu_mode = False
_op_confirmed_not_iwaparesu = False


def agent(obs_dict):
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return my_deck

    global _pre_turn_log, _current_turn_log

    state = obs.current
    select = obs.select
    context = select.context
    my_index = state.yourIndex
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]

    # --- Helper functions ---

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

    def calc_damage(energy_count):
        return 30 + 20 * energy_count

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
    for log in _pre_turn_log:
        if log.type == LogType.MOVE_CARD:
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
    bench_attacker = False
    has_fire_energy_on_field = False
    field_fire_energy_count = 0
    ogerpon_fire_energy_count = 0
    ogerpon_on_bench = False

    for card in my_state.active:
        if card is None:
            continue
        active_id = card.id
        field_counts[card.id] += 1
        if not card.appearThisTurn and card.id == Charcadet:
            can_evolve_charcadet = True
        if card.id == Ogerpon_Hearth:
            for ec in card.energyCards:
                if ec.id == Basic_Fire_Energy:
                    ogerpon_fire_energy_count += 1
        for ec in card.energyCards:
            if ec.id == Basic_Fire_Energy:
                has_fire_energy_on_field = True
                field_fire_energy_count += 1
    for card in my_state.bench:
        field_counts[card.id] += 1
        if not card.appearThisTurn and card.id == Charcadet:
            can_evolve_charcadet = True
        if card.id == Ceruledge_ex and len(card.energies) >= 1:
            bench_attacker = True
        if card.id == Ogerpon_Hearth:
            ogerpon_on_bench = True
            for ec in card.energyCards:
                if ec.id == Basic_Fire_Energy:
                    ogerpon_fire_energy_count += 1
        for ec in card.energyCards:
            if ec.id == Basic_Fire_Energy:
                has_fire_energy_on_field = True
                field_fire_energy_count += 1

    hand_energy_count = 0
    hand_fire_energy_count = 0
    hand_fighting_energy_count = 0
    hand_budew_count = 0

    for card in my_state.hand:
        hand_counts[card.id] += 1
        ctype = card_table[card.id].cardType
        if ctype == CardType.BASIC_ENERGY:
            hand_energy_count += 1
            if card.id == Basic_Fire_Energy:
                hand_fire_energy_count += 1
            elif card.id == Basic_Fighting_Energy:
                hand_fighting_energy_count += 1
        if card.id == Budew:
            hand_budew_count += 1

    hand_size = len(my_state.hand)

    # バトル場のアタッカーに炎エネルギーが付いているか
    active_has_fire_energy = False
    for card in my_state.active:
        if card is not None and card.id in (Ceruledge_ex, Charcadet):
            for ec in card.energyCards:
                if ec.id == Basic_Fire_Energy:
                    active_has_fire_energy = True

    discard_fire_energy_count = 0
    for card in my_state.discard:
        discard_counts[card.id] += 1
        if card_table[card.id].cardType == CardType.BASIC_ENERGY:
            discard_energy_count += 1
        if card.id == Basic_Fire_Energy:
            discard_fire_energy_count += 1

    main_pokemon_count = field_counts[Charcadet] + field_counts[Ceruledge_ex]
    current_damage = calc_damage(discard_energy_count)

    # リソース枯渇チェック（夜のタンカ用）
    # 炎エネ: デッキ7枚のうち、場+手札にないもの = 山札+サイド+トラッシュ
    fire_energy_available = field_fire_energy_count + hand_fire_energy_count
    fire_energy_scarce = fire_energy_available <= 2 and discard_fire_energy_count >= 5

    # ソウブレイズex: デッキ4枚のうち、場+手札にあるもの
    ceruledge_available = field_counts[Ceruledge_ex] + hand_counts.get(Ceruledge_ex, 0)
    ceruledge_in_trash = discard_counts.get(Ceruledge_ex, 0)
    ceruledge_scarce = ceruledge_in_trash >= 3

    # 追加のソウブレイズexが必要か
    op_remaining_prizes = len(op_state.prize)
    needed_ceruledge = (op_remaining_prizes + 1) // 2  # ceil(prizes / 2)
    need_more_ceruledge = field_counts[Ceruledge_ex] < needed_ceruledge

    # --- LO対策: 理想盤面判定 ---
    ceruledge_with_energy = 0
    for card in my_state.active:
        if card is not None and card.id == Ceruledge_ex and len(card.energies) >= 1:
            ceruledge_with_energy += 1
    for card in my_state.bench:
        if card.id == Ceruledge_ex and len(card.energies) >= 1:
            ceruledge_with_energy += 1
    ideal_board = ceruledge_with_energy >= 2
    lo_danger = my_state.deckCount <= 8

    # キチキギスex用のベンチ枠予約
    fezandipiti_on_field = field_counts[Fezandipiti_ex] > 0
    bench_count = len(my_state.bench)
    # キチキギスexが場にいなければベンチ1枠を空けておく
    bench_max_for_others = 4 if not fezandipiti_on_field else 5

    # --- 対イワパレスモード検知（一度検知したら試合中維持） ---
    global _iwaparesu_mode
    if state.turn == 0:
        _iwaparesu_mode = False
    if not _iwaparesu_mode:
        for card in op_state.active:
            if card is not None and card.id in (Ishizumai_A, Ishizumai_B, Iwaparesu):
                _iwaparesu_mode = True
        if not _iwaparesu_mode:
            for card in op_state.bench:
                if card.id in (Ishizumai_A, Ishizumai_B, Iwaparesu):
                    _iwaparesu_mode = True
    iwaparesu_mode = _iwaparesu_mode
    op_active_is_iwaparesu = False
    for card in op_state.active:
        if card is not None and card.id == Iwaparesu:
            op_active_is_iwaparesu = True

    # --- オーガポン3状態判定 ---
    # 相手が草以外のエネルギーを使っていたら「イワパレスではない」確定
    global _op_confirmed_not_iwaparesu
    if state.turn == 0:
        _op_confirmed_not_iwaparesu = False
    if not _op_confirmed_not_iwaparesu and not iwaparesu_mode:
        for card in op_state.active:
            if card is not None:
                for ec in card.energyCards:
                    if ec.id != Basic_Grass_Energy and card_table[ec.id].cardType in (CardType.BASIC_ENERGY, CardType.SPECIAL_ENERGY):
                        _op_confirmed_not_iwaparesu = True
        for card in op_state.bench:
            for ec in card.energyCards:
                if ec.id != Basic_Grass_Energy and card_table[ec.id].cardType in (CardType.BASIC_ENERGY, CardType.SPECIAL_ENERGY):
                    _op_confirmed_not_iwaparesu = True
        for card in op_state.discard:
            if card.id != Basic_Grass_Energy and card_table[card.id].cardType in (CardType.BASIC_ENERGY, CardType.SPECIAL_ENERGY):
                _op_confirmed_not_iwaparesu = True
    # 3状態: iwaparesu_mode(確定), _op_confirmed_not_iwaparesu(否定確定), どちらもFalse(不明)
    ogerpon_unnecessary = not iwaparesu_mode and _op_confirmed_not_iwaparesu

    # 後攻1ターン目かどうか
    is_going_second_turn1 = (state.turn <= 1 and my_index != state.firstPlayer)
    # ベンチにスボミーがいるか
    budew_on_bench = any(card.id == Budew for card in my_state.bench)

    # 後1でスボミーをバトル場に出すためのにげる判定
    do_retreat_for_budew = (is_going_second_turn1
                           and budew_on_bench
                           and active_id != Budew)

    # オーガポンをバトル場に出すためのにげる判定
    do_retreat_for_ogerpon = (iwaparesu_mode
                              and op_active_is_iwaparesu
                              and ogerpon_on_bench
                              and ogerpon_fire_energy_count >= 3
                              and active_id != Ogerpon_Hearth)

    # アタッカー入れ替え: ベンチにエネ付きソウブレイズexがいて、バトル場が非アタッカー
    do_retreat_for_attacker = (not do_retreat_for_budew
                               and not do_retreat_for_ogerpon
                               and active_id != Ceruledge_ex
                               and active_id != Budew
                               and bench_attacker)

    # キチキギスexがバトル場に出た場合のにげる判定
    do_retreat_for_fezandipiti = (active_id == Fezandipiti_ex
                                  and not do_retreat_for_budew
                                  and not do_retreat_for_ogerpon
                                  and not do_retreat_for_attacker
                                  and len(my_state.bench) > 0)

    # --- ボスの指令でワンパンできる相手exがいるか ---
    can_boss_ko_ex = False
    for card in op_state.bench:
        if card_table[card.id].ex and card.hp <= current_damage:
            can_boss_ko_ex = True

    # --- 対イワパレス時のボスの指令ターゲット ---
    boss_iwaparesu_target = False
    if iwaparesu_mode:
        for card in op_state.bench:
            if card.id in (Ishizumai_A, Ishizumai_B):
                boss_iwaparesu_target = True
                break
        if not boss_iwaparesu_target:
            for card in op_state.bench:
                if card.id != Iwaparesu:
                    boss_iwaparesu_target = True
                    break

    # --- サポート選択ロジック ---
    playable_supporters = set()
    if context == SelectContext.MAIN and not state.supporterPlayed:
        for o in select.option:
            if o.type == OptionType.PLAY:
                card = get_card(AreaType.HAND, o.index, my_index)
                if card_table[card.id].cardType == CardType.SUPPORTER:
                    playable_supporters.add(card.id)

    # ゼイユ使用条件: 捨てられるカード > 捨てたくないカード
    zeyu_discardable = hand_fighting_energy_count
    if discard_fire_energy_count < 4:
        zeyu_discardable += hand_fire_energy_count
    if not is_going_second_turn1:
        zeyu_discardable += hand_budew_count
    if ogerpon_unnecessary:
        zeyu_discardable += hand_counts.get(Ogerpon_Hearth, 0)
    zeyu_undiscardable = 0
    for card in my_state.hand:
        if card.id in (Ceruledge_ex, Charcadet, Perfect_Mixer):
            zeyu_undiscardable += 1
        elif card.id == Ogerpon_Hearth and not ogerpon_unnecessary:
            zeyu_undiscardable += 1
        elif iwaparesu_mode and card.id == Night_Stretcher:
            zeyu_undiscardable += 1
        elif card_table[card.id].cardType == CardType.SUPPORTER and card.id != Zeyu:
            zeyu_undiscardable += 1
    zeyu_preferred = zeyu_discardable > zeyu_undiscardable

    # LO対策: 理想盤面 or 山札8枚以下→ドローサポート禁止
    skip_draw_supporters = ideal_board or lo_danger

    use_support = 0
    if not state.supporterPlayed:
        if iwaparesu_mode and boss_iwaparesu_target and op_active_is_iwaparesu and Boss_Orders in playable_supporters:
            use_support = Boss_Orders
        elif can_boss_ko_ex and Boss_Orders in playable_supporters:
            use_support = Boss_Orders
        elif skip_draw_supporters:
            # ドローサポートを使わない（ボスの指令は上で処理済み）
            use_support = 0
        elif zeyu_preferred and Zeyu in playable_supporters:
            use_support = Zeyu
        elif Lillie_Determination in playable_supporters:
            use_support = Lillie_Determination
        elif Zeyu in playable_supporters:
            use_support = Zeyu

    # --- にげる判定 ---
    if active_id == Budew:
        do_switch = False
    elif do_retreat_for_budew:
        do_switch = True
    elif do_retreat_for_ogerpon:
        do_switch = True
    elif do_retreat_for_attacker:
        do_switch = True
    elif do_retreat_for_fezandipiti:
        do_switch = True
    else:
        do_switch = False

    # --- ドローソースのスコア制御 ---
    has_playable_cards = False
    if context == SelectContext.MAIN:
        for o in select.option:
            if o.type == OptionType.PLAY:
                card = get_card(AreaType.HAND, o.index, my_index)
                ctype = card_table[card.id].cardType
                if ctype != CardType.SUPPORTER and ctype != CardType.BASIC_ENERGY:
                    has_playable_cards = True
                    break
            elif o.type == OptionType.EVOLVE:
                has_playable_cards = True
                break

    if skip_draw_supporters:
        draw_support_score = -1  # LO対策: ドローサポート抑制
    elif has_playable_cards:
        draw_support_score = 14000
    else:
        draw_support_score = 90000

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
                        if card.id == Ogerpon_Hearth and do_retreat_for_ogerpon:
                            score += 200000
                        elif card.id == Ceruledge_ex:
                            score += 50000 + energy_count * 5000
                        elif card.id == Charcadet:
                            score += 10000
                        elif card.id == Budew:
                            if context == SelectContext.SETUP_ACTIVE_POKEMON:
                                score += 100000 if my_index != state.firstPlayer else 5000
                            elif do_retreat_for_budew:
                                score += 100000
                            else:
                                score += 3000
                        elif card.id == Ogerpon_Hearth:
                            score += 4000
                        elif card.id == Mogurew:
                            score += 12000 if do_retreat_for_fezandipiti else 2000
                        elif card.id == Fezandipiti_ex:
                            score += 1000
                        score += energy_count * 1000 + hp
                    else:
                        if iwaparesu_mode:
                            if card.id in (Ishizumai_A, Ishizumai_B):
                                score += 150000
                            elif card.id == Iwaparesu:
                                score += 1000
                            else:
                                score += 100000
                        else:
                            score += pokemon_score(card, True)
                            if hp <= current_damage:
                                score += 50000

                elif context == SelectContext.SETUP_BENCH_POKEMON:
                    # バトル開始前はモグリュー・オーガポンを出さない
                    if card.id == Charcadet:
                        score = 10000
                    else:
                        score = -1

                elif context == SelectContext.TO_BENCH:
                    # ポフィンの対象制限: カルボウ常時、スボミー後1のみ、オーガポン対イワパレス時のみ
                    is_from_poffin = select.effect is not None and select.effect.id == Buddy_Buddy_Poffin
                    if is_from_poffin:
                        if card.id == Ogerpon_Hearth and iwaparesu_mode:
                            score = 100000  # イワパレスモード: オーガポン最優先
                        elif card.id == Charcadet:
                            score = 50000  # カルボウ
                        elif card.id == Budew and is_going_second_turn1:
                            score = 40000  # 後1スボミー
                        else:
                            score = -1
                    elif card.id == Budew:
                        if is_going_second_turn1 and field_counts[Budew] == 0:
                            score = 100000
                        else:
                            score = -1
                    elif card.id == Ogerpon_Hearth:
                        if iwaparesu_mode:
                            score = 45000
                        else:
                            score = -1  # イワパレス確定以外はベンチに出さない
                    elif card.id == Charcadet:
                        if bench_count >= bench_max_for_others:
                            score = -1
                        elif main_pokemon_count >= 3:
                            score = -1
                        elif main_pokemon_count <= 1:
                            score = 50000
                        elif field_counts[Charcadet] < 2:
                            score = 20000
                        else:
                            score = 5000
                    elif card.id == Mogurew:
                        if bench_count >= bench_max_for_others:
                            score = -1
                        elif main_pokemon_count >= 2 and field_counts[Charcadet] >= 2:
                            score = 40000
                        elif main_pokemon_count >= 2:
                            score = 30000
                        else:
                            score = 8000
                    elif card.id == Fezandipiti_ex:
                        score = 10000
                    else:
                        score = 1000

                elif context == SelectContext.TO_HAND:
                    # きぜつ後のサーチ優先度 + パーフェクトミキサーのトラッシュ選択
                    if select.effect is not None and select.effect.id == Perfect_Mixer:
                        # パーフェクトミキサーでのトラッシュ選択
                        if card.id == Basic_Fighting_Energy:
                            score = 100000
                        elif lo_danger or ideal_board:
                            score = -1  # LO対策: 闘エネ以外捨てない
                        elif card.id == Budew and not is_going_second_turn1:
                            score = 80000
                        elif card.id == Ogerpon_Hearth and ogerpon_unnecessary:
                            score = 80000
                        elif card.id == Basic_Fire_Energy:
                            score = 70000 if field_fire_energy_count >= 3 else -1
                        else:
                            score = -1
                    else:
                        # 通常のサーチ先選択
                        # 対イワパレス時: オーガポンが場にいなければ最優先サーチ
                        if card.id == Ogerpon_Hearth and iwaparesu_mode and field_counts[Ogerpon_Hearth] == 0:
                            score = 55000
                        # リソース枯渇チェック（夜のタンカ用）
                        elif card.id == Basic_Fire_Energy and fire_energy_scarce:
                            score = 70000
                        elif card.id == Ceruledge_ex and ceruledge_scarce and need_more_ceruledge:
                            score = 65000
                        # アタッカー準備のボトルネック
                        elif card.id == Charcadet:
                            if field_counts[Charcadet] == 0 and field_counts[Ceruledge_ex] == 0:
                                score = 50000  # 場にカルボウがいない→最優先
                            else:
                                score = 5000  # カルボウがいるならソウブレイズex優先
                        elif card.id == Ceruledge_ex:
                            if field_counts[Charcadet] > 0 and field_counts[Ceruledge_ex] == 0:
                                score = 45000  # カルボウはいるがソウブレイズexがいない
                            elif field_counts[Ceruledge_ex] < 2:
                                score = 40000  # ソウブレイズex2体未満→追加
                            else:
                                score = 5000
                        elif card.id == Basic_Fire_Energy:
                            if not active_has_fire_energy and hand_fire_energy_count == 0:
                                score = 60000  # パターンC
                            else:
                                score = 10000
                        elif card.id == Fezandipiti_ex:
                            if field_counts[Ceruledge_ex] >= 2 and not fezandipiti_on_field:
                                score = 40000  # ソウブレイズex2体→キチキギスex
                            elif field_counts[Ceruledge_ex] >= 1:
                                score = 30000
                            else:
                                score = 100
                        elif card.id == Mogurew:
                            if field_counts[Ceruledge_ex] >= 2 and fezandipiti_on_field and field_counts[Mogurew] < 2:
                                score = 35000  # キチキギスも場にいる→モグリュー
                            elif field_counts[Mogurew] < 2:
                                score = 25000
                            else:
                                score = 5000
                        elif card.id == Budew:
                            if is_going_second_turn1 and field_counts[Budew] == 0:
                                score = 60000
                            else:
                                score = UNNECESSARY
                        elif card.id == Basic_Fighting_Energy:
                            # 闘エネは回収しない（トラッシュに残して火力にする）
                            score = -1
                        elif card.id == Ogerpon_Hearth:
                            score = UNNECESSARY if ogerpon_unnecessary else 3000
                        elif card.id == Night_Stretcher:
                            if iwaparesu_mode and discard_counts.get(Ogerpon_Hearth, 0) >= 1:
                                score = 55000
                            elif discard_counts[Ceruledge_ex] >= 1:
                                score = 30000
                            else:
                                score = 5000
                        else:
                            ctype = card_table[card.id].cardType
                            if ctype == CardType.SUPPORTER:
                                score = 8000
                            else:
                                score = 3000
                        # 重複チェック
                        if hand_counts.get(card.id, 0) > 0:
                            if card.id in (Charcadet, Basic_Fire_Energy, Basic_Fighting_Energy):
                                score -= 100
                            else:
                                score -= 100000
                        hand_counts[card.id] += 1

                elif context == SelectContext.DISCARD:
                    hand_counts[card.id] -= 1
                    card_data = card_table[card.id]
                    ctype = card_data.cardType

                    if card.id == Ogerpon_Hearth:
                        score = 60000 if ogerpon_unnecessary else -200000
                    elif card.id == Ceruledge_ex or card.id == Charcadet:
                        score = -200000
                    elif card.id == Budew:
                        score = -200000 if is_going_second_turn1 else 60000
                    elif ctype == CardType.POKEMON:
                        score = -150000
                    elif card.id == Perfect_Mixer:
                        score = -200000
                    elif card.id == Night_Stretcher and iwaparesu_mode:
                        score = -200000
                    elif ctype == CardType.SUPPORTER:
                        score = -200000
                    elif card.id == Basic_Fighting_Energy:
                        score = 110000
                    elif card.id == Basic_Fire_Energy:
                        if discard_fire_energy_count >= 4:
                            # トラッシュに炎エネが4枚以上→これ以上捨てない
                            score = -50000
                        elif has_fire_energy_on_field:
                            score = 100000
                        elif hand_fire_energy_count >= 2:
                            score = 100000
                        else:
                            score = -50000
                    elif ctype == CardType.BASIC_ENERGY:
                        score = 100000
                    else:
                        if card.id == Buddy_Buddy_Poffin and state.turn >= 3:
                            score = 50000
                        elif card.id == Fight_Gong and field_counts[Mogurew] >= 2:
                            score = 50000
                        else:
                            score = -10000

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

            # --- ポケモン ---
            if card.id == Charcadet:
                if bench_count >= bench_max_for_others or main_pokemon_count >= 3:
                    score = -1
                else:
                    score = 51000 if main_pokemon_count < 3 else 20000
            elif card.id == Mogurew:
                if bench_count >= bench_max_for_others:
                    score = -1
                elif field_counts[Mogurew] < 2:
                    score = 52000
                else:
                    score = -1
            elif card.id == Budew:
                if is_going_second_turn1 and field_counts[Budew] == 0:
                    score = 55000
                else:
                    score = -1
            elif card.id == Ogerpon_Hearth:
                if iwaparesu_mode:
                    score = 54000
                else:
                    score = -1  # イワパレス確定以外はベンチに出さない
            elif card.id == Fezandipiti_ex:
                score = 53000

            # --- グッズ ---
            elif card.id == Perfect_Mixer:
                # 山札に闘エネルギーがある場合のみ使う
                if deck_counts[Basic_Fighting_Energy] > 0:
                    score = 95000
                else:
                    score = -1
            elif card.id == Buddy_Buddy_Poffin:
                # ポフィン対象: 通常時カルボウのみ、イワパレスモード時オーガポン最優先
                poffin_has_target = False
                if iwaparesu_mode and deck_counts.get(Ogerpon_Hearth, 0) > 0 and field_counts[Ogerpon_Hearth] == 0:
                    poffin_has_target = True
                if deck_counts[Charcadet] > 0 and main_pokemon_count < 3:
                    poffin_has_target = True
                if is_going_second_turn1 and deck_counts[Budew] > 0 and field_counts[Budew] == 0:
                    poffin_has_target = True
                if not poffin_has_target:
                    score = -1
                else:
                    score = 49000
            elif card.id == Poke_Pad:
                # ポケパッド: カルボウ・モグリュー・オーガポンをサーチ
                if iwaparesu_mode and deck_counts.get(Ogerpon_Hearth, 0) > 0 and field_counts[Ogerpon_Hearth] == 0:
                    score = 46000
                elif deck_counts[Mogurew] > 0 and field_counts[Mogurew] < 2:
                    score = 46000
                elif deck_counts[Charcadet] > 0 and main_pokemon_count < 3:
                    score = 46000
                else:
                    score = -1
            elif card.id == Fight_Gong:
                if deck_counts[Mogurew] > 0 and field_counts[Mogurew] < 2:
                    score = 47000
                elif deck_counts[Basic_Fighting_Energy] > 0:
                    score = 45000
                else:
                    score = -1
            elif card.id == Ultra_Ball:
                discardable = hand_fighting_energy_count
                if has_fire_energy_on_field or hand_fire_energy_count >= 2:
                    discardable += hand_fire_energy_count
                else:
                    discardable += max(0, hand_fire_energy_count - 1)
                for hc in my_state.hand:
                    hcid = hc.id
                    hctype = card_table[hcid].cardType
                    if hctype not in (CardType.POKEMON, CardType.SUPPORTER, CardType.BASIC_ENERGY, CardType.SPECIAL_ENERGY):
                        if hcid not in (Perfect_Mixer, Ultra_Ball):
                            if hcid == Buddy_Buddy_Poffin and state.turn >= 3:
                                discardable += 1
                            elif hcid == Fight_Gong and field_counts[Mogurew] >= 2:
                                discardable += 1

                if discardable >= 2:
                    score = 45000
                elif discardable >= 1 and main_pokemon_count <= 2:
                    score = 42000
                else:
                    score = -1
            elif card.id == Night_Stretcher:
                if iwaparesu_mode:
                    # 対イワパレス時: トラッシュにオーガポンがいる場合のみ使用
                    if discard_counts.get(Ogerpon_Hearth, 0) > 0:
                        score = 44000
                    else:
                        score = -1
                # リソース枯渇チェック
                elif fire_energy_scarce and discard_fire_energy_count > 0:
                    score = 44000
                elif ceruledge_scarce and need_more_ceruledge and discard_counts.get(Ceruledge_ex, 0) > 0:
                    score = 44000
                # アタッカー準備のボトルネック
                elif main_pokemon_count == 0 and discard_counts.get(Charcadet, 0) > 0:
                    score = 44000  # パターンA
                elif field_counts[Charcadet] > 0 and field_counts[Ceruledge_ex] == 0 and discard_counts.get(Ceruledge_ex, 0) > 0:
                    score = 44000  # パターンB
                elif not active_has_fire_energy and hand_fire_energy_count == 0 and discard_fire_energy_count > 0:
                    score = 44000  # パターンC
                # ソウブレイズexも炎エネも足りているなら使わない
                else:
                    score = -1
            elif card.id == Switch:
                score = 38000 if do_switch else -1

            # --- サポート ---
            elif card.id == Zeyu:
                score = draw_support_score if card.id == use_support else -1
            elif card.id == Lillie_Determination:
                score = draw_support_score if card.id == use_support else -1
            elif card.id == Boss_Orders:
                if card.id == use_support:
                    score = 93000 if iwaparesu_mode else 35000
                else:
                    score = -1

        elif o.type == OptionType.ATTACH:
            card = get_card(o.area, o.index, my_index)
            pokemon = get_card(o.inPlayArea, o.inPlayIndex, my_index)
            is_active = o.inPlayArea == AreaType.ACTIVE
            p_energy_count = len(pokemon.energies)

            # 後攻1ターン目: にげるコスト用の手貼り
            if do_retreat_for_budew and is_active:
                score = 85000
            # オーガポンをバトル場に出すためのにげるコスト用手貼り
            elif do_retreat_for_ogerpon and is_active and p_energy_count == 0:
                score = 92000
            # アタッカー入れ替え用の手貼り
            elif do_retreat_for_attacker and is_active and p_energy_count == 0:
                score = 92000
            # キチキギスex退避用の手貼り
            elif do_retreat_for_fezandipiti and is_active and p_energy_count == 0:
                score = 92000
            # 対イワパレス時: オーガポンにエネルギーを付ける（3枚まで）
            elif iwaparesu_mode and op_active_is_iwaparesu and pokemon.id == Ogerpon_Hearth and card.id == Basic_Fire_Energy and p_energy_count < 3:
                score = 86000
            # オーガポンはエネルギー3枚まで付けられる
            elif pokemon.id == Ogerpon_Hearth and card.id == Basic_Fire_Energy and p_energy_count < 3 and iwaparesu_mode:
                score = 86000
            # エネルギーが1枚以上付いているポケモンには付けない
            elif p_energy_count >= 1:
                score = -1
            elif card.id == Basic_Fighting_Energy:
                score = -1
            elif card_table[card.id].cardType == CardType.TOOL:
                score = 60000 + (1000 if is_active else 0)
            elif card.id == Basic_Fire_Energy:
                if pokemon.id == Ceruledge_ex:
                    if iwaparesu_mode and op_active_is_iwaparesu:
                        score = -1  # イワパレスがバトル場にいるときはソウブレイズexに付けない
                    else:
                        score = 90000 if is_active else 86000
                elif pokemon.id == Charcadet:
                    if iwaparesu_mode and op_active_is_iwaparesu:
                        score = -1
                    else:
                        score = 88000 if is_active else 84000
                else:
                    score = -1
            else:
                score = -1

        elif o.type == OptionType.EVOLVE:
            pokemon = get_card(o.inPlayArea, o.inPlayIndex, my_index)
            score = (70000 + len(pokemon.energies)) if pokemon.id == Charcadet else -1

        elif o.type == OptionType.ABILITY:
            card = get_card(o.area, o.index, my_index)
            if card.id == Mogurew:
                score = 60000
            elif card.id == Fezandipiti_ex:
                score = 75000 if pre_ko else 40000
            elif card.id == 1267:
                score = 1
            else:
                score = 40000

        elif o.type == OptionType.RETREAT:
            if do_retreat_for_budew:
                score = 82000
            elif do_retreat_for_ogerpon:
                score = 91000
            elif do_retreat_for_attacker:
                score = 91000
            elif do_retreat_for_fezandipiti:
                score = 91000
            elif do_switch:
                score = 10000
            else:
                score = -1

        elif o.type == OptionType.ATTACK:
            score = o.attackId if o.attackId > 0 else 1

        scores.append(score)

    # --- Build output ---
    is_perfect_mixer_select = (context == SelectContext.TO_HAND
                               and select.effect is not None
                               and select.effect.id == Perfect_Mixer)
    output = []
    if len(scores) >= 1:
        sorted_scores = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        for i in range(select.maxCount):
            if i >= len(sorted_scores):
                break
            if (sorted_scores[i][1] >= 0
                or select.minCount > i
                or (context != SelectContext.TO_BENCH
                    and context != SelectContext.SETUP_BENCH_POKEMON
                    and not is_perfect_mixer_select)):
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
