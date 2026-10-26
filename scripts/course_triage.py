"""Read-only incident triage practice (chapter 09): static outputs, stop/continue, what to report. Pure logic."""

SCENARIOS = [
    {
        'id': 'a',
        'title': 'Reason 不是你的',
        'context': '第 09 章練習做到一半，你準備 RESUME cpu02。',
        'output': (
            '$ sinfo -N -o "%N %t %E"\n'
            'NODELIST STATE REASON\n'
            'cpu01 idle none\n'
            'cpu02 drain admin-kernel-upgrade\n'
            'gpu01 idle none\n'
        ),
        'decision': 'stop',
        'facts': [
            ('output', '完整指令與輸出（sinfo -N -o "%N %t %E"）'),
            ('node', 'cpu02 是 drain，Reason=admin-kernel-upgrade，不是你的 course-<代碼>'),
            ('time', '你看到這個狀態的時間'),
            ('untouched', '你還沒有對 cpu02 做任何變更'),
            ('resumed', '我已先 RESUME cpu02，看看會不會恢復'),
            ('rewrote', '我把 Reason 改回 course-<代碼> 再 RESUME'),
        ],
        'required': {'output', 'node', 'time', 'untouched'},
        'wrong': {'resumed', 'rewrote'},
        'explanation': (
            'Reason 是 DRAIN 的所有權標記；不是你的 Reason，就是別人的維護。'
            'RESUME 會讓排程器把新工作送到可能正在升級的節點。停手，附上輸出問管理者；'
            '如果你自己的 DRAIN 被覆蓋了，也一併說明。'
        ),
    },
    {
        'id': 'b',
        'title': 'DRAIN 前，cpu02 上有別人的工作',
        'context': '你準備 DRAIN cpu02 做維運練習，先看節點上有什麼工作。',
        'output': (
            '$ squeue -w cpu02 -o "%.6i %.9P %.14j %.8u %.2t %.10M %R"\n'
            ' JOBID PARTITION           NAME     USER ST       TIME NODELIST(REASON)\n'
            '   812       cpu   train-resnet    alice  R    2:13:05 cpu02\n'
        ),
        'decision': 'stop',
        'facts': [
            ('output', '完整指令與輸出（squeue -w cpu02 …）'),
            ('job', '別人的工作：ID 812、名稱 train-resnet、使用者 alice、已跑 2:13:05'),
            ('intent', '你原本要做什麼（DRAIN cpu02 做練習）'),
            ('untouched', '你還沒有 DRAIN，也沒有動 812'),
            ('cancelled', '我已 scancel 812，讓節點空出來'),
            ('drained', '我先 DRAIN 了，反正 DRAIN 不會殺掉正在跑的工作'),
        ],
        'required': {'output', 'job', 'untouched'},
        'wrong': {'cancelled', 'drained'},
        'explanation': (
            'DRAIN 確實不會殺掉 812，但會擋住所有人之後送到 cpu02 的工作，'
            '而且練習的前提是節點上只有你的工作。不能取消別人的工作。停手，等節點空出來或改天練習；'
            '要占用共用節點做維護，由管理者排時間。'
        ),
    },
    {
        'id': 'c',
        'title': 'controller 不是 UP',
        'context': '你要開始今天的練習，先確認 controller。',
        'output': (
            '$ scontrol ping\n'
            'Slurmctld(primary) at controller is DOWN\n'
            '$ squeue --me\n'
            'slurm_load_jobs error: Unable to contact slurm controller (connect failure)\n'
        ),
        'decision': 'stop',
        'facts': [
            ('output', '兩條指令的完整輸出'),
            ('time', '你看到的時間；上一次正常的時間（例如 10 分鐘前 squeue 還正常）'),
            ('untouched', '你沒有重啟任何服務，也沒有重送工作'),
            ('restarted', '我已重啟 controller（或 slurmctld）'),
            ('resubmitted', '我把工作重送了幾次，看哪次會成功'),
        ],
        'required': {'output', 'time', 'untouched'},
        'wrong': {'restarted', 'resubmitted'},
        'explanation': (
            'controller 沒回應時看不到 queue 與節點狀態，任何維護都無法確認影響。'
            '已在跑的工作通常繼續在計算節點上跑；重送只會在恢復後變成重複工作。'
            '第 09 章的重啟是教材在受控條件下做的；正式叢集只有管理者能重啟 slurmctld。'
        ),
    },
    {
        'id': 'd',
        'title': '節點 DOWN／NOT_RESPONDING',
        'context': '你要把工作送到 cpu01，先看節點狀態。',
        'output': (
            '$ sinfo -N -o "%N %t %E"\n'
            'NODELIST STATE REASON\n'
            'cpu01 down* Not responding\n'
            'cpu02 idle none\n'
            'gpu01 idle none\n'
            '$ scontrol show node cpu01 | grep -E "State=|Reason="\n'
            '   State=DOWN+NOT_RESPONDING ThreadsPerCore=2 TmpDisk=0 Weight=1 Owner=N/A MCS_label=N/A\n'
            '   Reason=Not responding [slurm@2026-10-24T14:20:03]\n'
        ),
        'decision': 'stop',
        'facts': [
            ('output', '兩條指令的完整輸出'),
            ('node', 'cpu01：State=DOWN+NOT_RESPONDING，Reason=Not responding，由 slurm 在 14:20:03 設定'),
            ('untouched', '你沒有 RESUME 或重啟 cpu01'),
            ('resumed', '我 RESUME 了 cpu01，讓它回來'),
            ('rebooted', '我重啟了 cpu01'),
        ],
        'required': {'output', 'node', 'untouched'},
        'wrong': {'resumed', 'rebooted'},
        'explanation': (
            '`*` 與 NOT_RESPONDING 表示 controller 連不到該節點的 slurmd；Reason 由 slurm 自動填入。'
            '這不是 DRAIN：RESUME 修不好通訊，節點會再變 DOWN，或把工作送到壞掉的節點。'
            '查 slurmd、網路與硬體是管理者的事；你的工作可以先送到其他健康節點。'
        ),
    },
    {
        'id': 'e',
        'title': 'slurmd 連不上 controller、munge 認證失敗',
        'context': '管理者給你唯讀權限看 cpu02 的 slurmd log。',
        'output': (
            '$ journalctl -u slurmd -n 3 --no-pager\n'
            'Oct 24 14:22:15 cpu02 slurmd[1234]: error: Unable to contact slurm controller (connect failure)\n'
            'Oct 24 14:22:16 cpu02 slurmd[1234]: error: Munge decode failed: Invalid credential\n'
            'Oct 24 14:22:17 cpu02 slurmd[1234]: error: Unable to contact slurm controller (connect failure)\n'
        ),
        'decision': 'stop',
        'facts': [
            ('output', '指令與 log 原文（不要只寫「有錯誤」）'),
            ('errors', '兩種錯誤：Unable to contact slurm controller、Munge decode failed: Invalid credential'),
            ('time', '第一次出現的時間，以及是否持續'),
            ('untouched', '你沒有重啟服務、沒有動 munge key'),
            ('restarted', '我重啟了 slurmd 和 munge'),
            ('newkey', '我重新產生並複製了 munge key'),
        ],
        'required': {'output', 'errors', 'time', 'untouched'},
        'wrong': {'restarted', 'newkey'},
        'explanation': (
            '連不到 controller 加上 munge 憑證無效，常見原因是 munge key 不一致、時鐘不同步或網路問題。'
            '重新產生 munge key 會讓整個叢集的認證失效。這是管理者的範圍；你提供原文與時間就好。'
        ),
    },
    {
        'id': 'f',
        'title': '自己的 DRAIN 期間，probe 在等',
        'context': '第 09 章：你剛用自己的代碼 c12345678 DRAIN cpu02，並送出 probe。',
        'output': (
            '$ sinfo -N -o "%N %t %E"\n'
            'NODELIST STATE REASON\n'
            'cpu01 idle none\n'
            'cpu02 drain course-c12345678\n'
            'gpu01 idle none\n'
            '$ squeue --me -o "%.6i %.26j %.2t %R"\n'
            ' JOBID                       NAME ST NODELIST(REASON)\n'
            '  1024   course-c12345678-probe PD (ReqNodeNotAvail, May be reserved for other job)\n'
        ),
        'decision': 'continue',
        'facts': [
            ('own_reason', '確認 cpu02 的 Reason 就是自己的 course-c12345678'),
            ('own_job', '確認 PENDING 的是自己的 probe（course-c12345678-probe）'),
            ('escalated', '回報管理者：cpu02 故障，我的工作卡住了'),
            ('cancelled', '我取消 probe，因為它卡住了'),
        ],
        'required': {'own_reason', 'own_job'},
        'wrong': {'escalated', 'cancelled'},
        'explanation': (
            'ReqNodeNotAvail 正是 DRAIN 的預期效果：節點不收新工作。probe 會一直等到你 RESUME，'
            '不會因為時間到就自己開始。Reason 與工作都是自己的，照第 09 章繼續：確認等待證據後再 RESUME。'
        ),
    },
    {
        'id': 'g',
        'title': '自己的工作 PENDING（Resources）',
        'context': '你送了一個申請 4 CPU 的工作，想知道為什麼還沒開始。',
        'output': (
            '$ squeue -p cpu -o "%.6i %.10j %.6u %.2t %.4C %R"\n'
            ' JOBID       NAME   USER ST CPUS NODELIST(REASON)\n'
            '  2050     my-sim    lab PD    4 (Resources)\n'
            '  2047   holder-a    bob  R    4 cpu01\n'
            '  2048   holder-b  carol  R    4 cpu02\n'
            '$ sinfo -N -o "%N %t %E"\n'
            'NODELIST STATE REASON\n'
            'cpu01 alloc none\n'
            'cpu02 alloc none\n'
            'gpu01 idle none\n'
        ),
        'decision': 'continue',
        'facts': [
            ('reason', '確認 Reason 是 Resources：cpu partition 的 CPU 都被正在跑的工作占用'),
            ('nodes', '確認節點是 alloc，沒有 drain／down'),
            ('cancelled', '我取消了 2047、2048，讓我的工作先跑'),
            ('drained', '我 DRAIN cpu01，讓它跑完後只留給我'),
        ],
        'required': {'reason', 'nodes'},
        'wrong': {'cancelled', 'drained'},
        'explanation': (
            'PENDING (Resources) 是正常排隊，不是事故：等 2047／2048 結束就會輪到你。'
            'gpu01 雖然 idle，但它在 gpu partition，不會接 cpu partition 的工作。'
            '可以等，或在合理範圍內縮小申請；不能取消或擋住別人的工作。'
        ),
    },
]


DECISIONS = {'stop': '停手，找管理者', 'continue': '繼續'}


def grade_triage(scenario_id, decision, selected_keys):
    """Grade one triage answer: the decision, every required report fact, and no harmful fact.

    Returns {'passed', 'items' (項目/結果/說明), 'explanation'}; unknown ids raise KeyError.
    """
    scenario = next((s for s in SCENARIOS if s['id'] == scenario_id), None)
    if scenario is None:
        raise KeyError(f'Unknown scenario: {scenario_id}')
    texts = dict(scenario['facts'])
    selected = set(selected_keys or ())
    expected = DECISIONS[scenario['decision']]
    if not decision:
        items = [{'項目': '判斷', '結果': '✗', '說明': '未選擇「繼續」或「停手，找管理者」'}]
    elif decision != scenario['decision']:
        items = [{'項目': '判斷', '結果': '✗', '說明': f"應該是「{expected}」，你選了「{DECISIONS.get(decision, decision)}」"}]
    else:
        items = [{'項目': '判斷', '結果': '✓', '說明': expected}]
    items += [{'項目': '必要資訊', '結果': '✗', '說明': f'沒有勾選：{texts[key]}'}
              for key in sorted(scenario['required'] - selected)]
    items += [{'項目': '不該勾選', '結果': '✗', '說明': f'{texts[key]}：這是有害或不必要的操作'}
              for key in sorted(selected & scenario['wrong'])]
    passed = all(item['結果'] == '✓' for item in items)
    if passed:
        items.append({'項目': '回報資訊', '結果': '✓', '說明': '必要資訊都有勾，沒有勾有害操作'})
    return {'passed': passed, 'items': items, 'explanation': scenario['explanation']}
