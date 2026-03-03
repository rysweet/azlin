# Azlin Feature Scorecard

Generated: 2026-03-03 09:48:08 UTC

| Feature | Agentic Test | Python Works | Rust Works | Python (ms) | Rust (ms) | Speedup |
|---------|:---:|:---:|:---:|---:|---:|---:|
| `list` | ✅ | ✅ | ✅ | 725 | 14 | 51x |
| `new` | ✅ | ✅ | ✅ | 702 | 14 | 50x |
| `start` | ✅ | ✅ | ✅ | 699 | 13 | 53x |
| `stop` | ✅ | ✅ | ✅ | 699 | 14 | 49x |
| `connect` | ✅ | ✅ | ✅ | 689 | 13 | 53x |
| `status` | ✅ | ✅ | ✅ | 688 | 13 | 52x |
| `health` | ✅ | ✅ | ✅ | 690 | 13 | 53x |
| `cost` | ✅ | ✅ | ✅ | 710 | 13 | 54x |
| `ask` | ⬜ | ✅ | ✅ | 745 | 13 | 57x |
| `do` | ✅ | ❌ | ✅ | 748 | 13 | 57x |
| `clone` | ✅ | ✅ | ✅ | 731 | 15 | 48x |
| `cp` | ✅ | ✅ | ✅ | 730 | 14 | 52x |
| `sync` | ✅ | ✅ | ✅ | 729 | 13 | 56x |
| `sync-keys` | ⬜ | ✅ | ✅ | 745 | 13 | 57x |
| `code` | ✅ | ✅ | ✅ | 717 | 13 | 55x |
| `logs` | ✅ | ✅ | ✅ | 704 | 13 | 54x |
| `top` | ✅ | ✅ | ✅ | 691 | 13 | 53x |
| `kill` | ⬜ | ✅ | ✅ | 706 | 13 | 54x |
| `killall` | ⬜ | ✅ | ✅ | 700 | 13 | 53x |
| `destroy` | ✅ | ✅ | ✅ | 724 | 14 | 51x |
| `update` | ✅ | ✅ | ✅ | 701 | 14 | 50x |
| `os-update` | ✅ | ✅ | ✅ | 688 | 13 | 52x |
| `restore` | ✅ | ✅ | ✅ | 690 | 14 | 49x |
| `ps` | ✅ | ✅ | ✅ | 694 | 14 | 49x |
| `w` | ✅ | ✅ | ✅ | 699 | 14 | 49x |
| `session` | ✅ | ✅ | ✅ | 703 | 14 | 50x |
| `env set` | ✅ | ✅ | ✅ | 700 | 13 | 53x |
| `env list` | ✅ | ✅ | ✅ | 697 | 14 | 49x |
| `env delete` | ✅ | ✅ | ✅ | 695 | 14 | 49x |
| `env export` | ✅ | ✅ | ✅ | 691 | 14 | 49x |
| `env import` | ✅ | ✅ | ✅ | 700 | 14 | 50x |
| `env clear` | ✅ | ✅ | ✅ | 701 | 14 | 50x |
| `config show` | ✅ | ❌ | ✅ | 698 | 14 | 49x |
| `config set` | ✅ | ❌ | ✅ | 708 | 13 | 54x |
| `config get` | ✅ | ❌ | ✅ | 729 | 12 | 60x |
| `snapshot create` | ✅ | ✅ | ✅ | 755 | 13 | 58x |
| `snapshot list` | ✅ | ✅ | ✅ | 709 | 13 | 54x |
| `snapshot restore` | ✅ | ✅ | ✅ | 738 | 14 | 52x |
| `snapshot delete` | ✅ | ✅ | ✅ | 713 | 13 | 54x |
| `storage create` | ✅ | ✅ | ✅ | 720 | 14 | 51x |
| `storage list` | ✅ | ✅ | ✅ | 733 | 13 | 56x |
| `storage status` | ✅ | ✅ | ✅ | 705 | 13 | 54x |
| `storage mount` | ✅ | ✅ | ✅ | 719 | 13 | 55x |
| `storage unmount` | ✅ | ✅ | ✅ | 717 | 14 | 51x |
| `storage delete` | ✅ | ✅ | ✅ | 708 | 13 | 54x |
| `keys rotate` | ✅ | ✅ | ✅ | 707 | 15 | 47x |
| `keys list` | ✅ | ✅ | ✅ | 715 | 13 | 55x |
| `keys export` | ✅ | ✅ | ✅ | 705 | 14 | 50x |
| `keys backup` | ✅ | ✅ | ✅ | 712 | 13 | 54x |
| `auth setup` | ✅ | ✅ | ✅ | 710 | 14 | 50x |
| `auth test` | ✅ | ✅ | ✅ | 713 | 13 | 54x |
| `auth list` | ✅ | ✅ | ✅ | 706 | 13 | 54x |
| `auth show` | ✅ | ✅ | ✅ | 705 | 14 | 50x |
| `auth remove` | ✅ | ✅ | ✅ | 712 | 14 | 50x |
| `tag add` | ✅ | ✅ | ✅ | 715 | 13 | 55x |
| `tag remove` | ✅ | ✅ | ✅ | 695 | 13 | 53x |
| `tag list` | ✅ | ✅ | ✅ | 685 | 13 | 52x |
| `batch stop` | ✅ | ✅ | ✅ | 703 | 13 | 54x |
| `batch start` | ✅ | ✅ | ✅ | 692 | 13 | 53x |
| `batch command` | ✅ | ✅ | ✅ | 711 | 14 | 50x |
| `fleet run` | ✅ | ✅ | ✅ | 711 | 14 | 50x |
| `fleet workflow` | ✅ | ✅ | ✅ | 693 | 14 | 49x |
| `compose up` | ✅ | ✅ | ✅ | 697 | 14 | 49x |
| `compose down` | ✅ | ✅ | ✅ | 701 | 14 | 50x |
| `compose ps` | ✅ | ✅ | ✅ | 703 | 14 | 50x |
| `template create` | ✅ | ✅ | ✅ | 702 | 14 | 50x |
| `template list` | ✅ | ✅ | ✅ | 695 | 14 | 49x |
| `template delete` | ✅ | ✅ | ✅ | 699 | 13 | 53x |
| `template save` | ✅ | ❌ | ✅ | 702 | 13 | 54x |
| `template show` | ✅ | ❌ | ✅ | 696 | 14 | 49x |
| `template apply` | ✅ | ❌ | ✅ | 695 | 13 | 53x |
| `autopilot enable` | ✅ | ✅ | ✅ | 700 | 14 | 50x |
| `autopilot disable` | ✅ | ✅ | ✅ | 703 | 14 | 50x |
| `autopilot status` | ✅ | ✅ | ✅ | 700 | 14 | 50x |
| `context list` | ✅ | ✅ | ✅ | 712 | 13 | 54x |
| `context current` | ✅ | ✅ | ✅ | 698 | 14 | 49x |
| `context use` | ✅ | ✅ | ✅ | 702 | 14 | 50x |
| `context create` | ✅ | ✅ | ✅ | 712 | 14 | 50x |
| `context delete` | ✅ | ✅ | ✅ | 699 | 14 | 49x |
| `context rename` | ✅ | ✅ | ✅ | 699 | 13 | 53x |
| `disk add` | ✅ | ✅ | ✅ | 718 | 14 | 51x |
| `ip check` | ✅ | ✅ | ✅ | 699 | 14 | 49x |
| `web start` | ✅ | ✅ | ✅ | 712 | 14 | 50x |
| `web stop` | ✅ | ✅ | ✅ | 700 | 14 | 50x |
| `costs dashboard` | ✅ | ✅ | ✅ | 707 | 14 | 50x |
| `costs history` | ✅ | ✅ | ✅ | 696 | 14 | 49x |
| `costs budget` | ✅ | ✅ | ✅ | 703 | 14 | 50x |
| `costs recommend` | ✅ | ✅ | ✅ | 721 | 14 | 51x |
| `costs actions` | ✅ | ✅ | ✅ | 723 | 13 | 55x |
| `github-runner enable` | ✅ | ✅ | ✅ | 694 | 14 | 49x |
| `github-runner disable` | ✅ | ✅ | ✅ | 701 | 13 | 53x |
| `github-runner status` | ✅ | ✅ | ✅ | 688 | 13 | 52x |
| `github-runner scale` | ✅ | ✅ | ✅ | 684 | 13 | 52x |
| `doit deploy` | ⬜ | ✅ | ✅ | 736 | 13 | 56x |
| `sessions save` | ✅ | ✅ | ✅ | 703 | 13 | 54x |
| `sessions list` | ✅ | ✅ | ✅ | 693 | 13 | 53x |
| `sessions load` | ✅ | ✅ | ✅ | 696 | 14 | 49x |
| `sessions delete` | ✅ | ❌ | ✅ | 708 | 14 | 50x |
| `bastion list` | ⬜ | ✅ | ✅ | 699 | 14 | 49x |
| `bastion status` | ⬜ | ✅ | ✅ | 682 | 14 | 48x |
| `bastion configure` | ⬜ | ✅ | ✅ | 683 | 14 | 48x |
| `completions bash` | ✅ | ❌ | ✅ | 704 | 15 | 46x |

## Summary

- **Total commands tested**: 102
- **Python passing**: 93 / 102
- **Rust passing**: 102 / 102
- **With agentic tests**: 94 / 102
