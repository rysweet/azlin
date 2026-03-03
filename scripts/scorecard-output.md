# Azlin Feature Scorecard

Generated: 2026-03-03 11:19:40 UTC

| Feature | Agentic Test | Python Works | Rust Works | Python (ms) | Rust (ms) | Speedup |
|---------|:---:|:---:|:---:|---:|---:|---:|
| `list` | ✅ | ✅ | ✅ | 710 | 13 | 54x |
| `new` | ✅ | ✅ | ✅ | 700 | 14 | 50x |
| `start` | ✅ | ✅ | ✅ | 704 | 14 | 50x |
| `stop` | ✅ | ✅ | ✅ | 702 | 14 | 50x |
| `connect` | ✅ | ✅ | ✅ | 713 | 14 | 50x |
| `status` | ✅ | ✅ | ✅ | 705 | 13 | 54x |
| `health` | ✅ | ✅ | ✅ | 729 | 13 | 56x |
| `cost` | ✅ | ✅ | ✅ | 711 | 13 | 54x |
| `ask` | ✅ | ✅ | ✅ | 713 | 14 | 50x |
| `do` | ✅ | ❌ | ✅ | 727 | 14 | 51x |
| `clone` | ✅ | ✅ | ✅ | 722 | 14 | 51x |
| `cp` | ✅ | ✅ | ✅ | 719 | 14 | 51x |
| `sync` | ✅ | ✅ | ✅ | 689 | 13 | 53x |
| `sync-keys` | ✅ | ✅ | ✅ | 694 | 14 | 49x |
| `code` | ✅ | ✅ | ✅ | 704 | 14 | 50x |
| `logs` | ✅ | ✅ | ✅ | 686 | 14 | 49x |
| `top` | ✅ | ✅ | ✅ | 696 | 14 | 49x |
| `kill` | ✅ | ✅ | ✅ | 685 | 13 | 52x |
| `killall` | ✅ | ✅ | ✅ | 712 | 14 | 50x |
| `destroy` | ✅ | ✅ | ✅ | 695 | 14 | 49x |
| `update` | ✅ | ✅ | ✅ | 692 | 13 | 53x |
| `os-update` | ✅ | ✅ | ✅ | 701 | 15 | 46x |
| `restore` | ✅ | ✅ | ✅ | 709 | 14 | 50x |
| `ps` | ✅ | ✅ | ✅ | 694 | 14 | 49x |
| `w` | ✅ | ✅ | ✅ | 702 | 13 | 54x |
| `session` | ✅ | ✅ | ✅ | 694 | 13 | 53x |
| `env set` | ✅ | ✅ | ✅ | 693 | 14 | 49x |
| `env list` | ✅ | ✅ | ✅ | 700 | 14 | 50x |
| `env delete` | ✅ | ✅ | ✅ | 691 | 14 | 49x |
| `env export` | ✅ | ✅ | ✅ | 696 | 14 | 49x |
| `env import` | ✅ | ✅ | ✅ | 695 | 13 | 53x |
| `env clear` | ✅ | ✅ | ✅ | 705 | 14 | 50x |
| `config show` | ✅ | ❌ | ✅ | 699 | 14 | 49x |
| `config set` | ✅ | ❌ | ✅ | 701 | 13 | 53x |
| `config get` | ✅ | ❌ | ✅ | 696 | 13 | 53x |
| `snapshot create` | ✅ | ✅ | ✅ | 684 | 13 | 52x |
| `snapshot list` | ✅ | ✅ | ✅ | 692 | 13 | 53x |
| `snapshot restore` | ✅ | ✅ | ✅ | 702 | 13 | 54x |
| `snapshot delete` | ✅ | ✅ | ✅ | 730 | 13 | 56x |
| `storage create` | ✅ | ✅ | ✅ | 687 | 13 | 52x |
| `storage list` | ✅ | ✅ | ✅ | 692 | 14 | 49x |
| `storage status` | ✅ | ✅ | ✅ | 700 | 14 | 50x |
| `storage mount` | ✅ | ✅ | ✅ | 700 | 13 | 53x |
| `storage unmount` | ✅ | ✅ | ✅ | 716 | 14 | 51x |
| `storage delete` | ✅ | ✅ | ✅ | 709 | 14 | 50x |
| `keys rotate` | ✅ | ✅ | ✅ | 724 | 13 | 55x |
| `keys list` | ✅ | ✅ | ✅ | 703 | 13 | 54x |
| `keys export` | ✅ | ✅ | ✅ | 706 | 12 | 58x |
| `keys backup` | ✅ | ✅ | ✅ | 700 | 13 | 53x |
| `auth setup` | ✅ | ✅ | ✅ | 688 | 13 | 52x |
| `auth test` | ✅ | ✅ | ✅ | 700 | 13 | 53x |
| `auth list` | ✅ | ✅ | ✅ | 697 | 13 | 53x |
| `auth show` | ✅ | ✅ | ✅ | 689 | 13 | 53x |
| `auth remove` | ✅ | ✅ | ✅ | 700 | 13 | 53x |
| `tag add` | ✅ | ✅ | ✅ | 707 | 13 | 54x |
| `tag remove` | ✅ | ✅ | ✅ | 684 | 12 | 57x |
| `tag list` | ✅ | ✅ | ✅ | 694 | 12 | 57x |
| `batch stop` | ✅ | ✅ | ✅ | 702 | 13 | 54x |
| `batch start` | ✅ | ✅ | ✅ | 692 | 13 | 53x |
| `batch command` | ✅ | ✅ | ✅ | 698 | 13 | 53x |
| `fleet run` | ✅ | ✅ | ✅ | 701 | 13 | 53x |
| `fleet workflow` | ✅ | ✅ | ✅ | 696 | 13 | 53x |
| `compose up` | ✅ | ✅ | ✅ | 693 | 13 | 53x |
| `compose down` | ✅ | ✅ | ✅ | 692 | 13 | 53x |
| `compose ps` | ✅ | ✅ | ✅ | 683 | 13 | 52x |
| `template create` | ✅ | ✅ | ✅ | 709 | 13 | 54x |
| `template list` | ✅ | ✅ | ✅ | 701 | 13 | 53x |
| `template delete` | ✅ | ✅ | ✅ | 688 | 16 | 43x |
| `template save` | ✅ | ❌ | ✅ | 698 | 14 | 49x |
| `template show` | ✅ | ❌ | ✅ | 715 | 14 | 51x |
| `template apply` | ✅ | ❌ | ✅ | 714 | 14 | 51x |
| `autopilot enable` | ✅ | ✅ | ✅ | 698 | 14 | 49x |
| `autopilot disable` | ✅ | ✅ | ✅ | 700 | 13 | 53x |
| `autopilot status` | ✅ | ✅ | ✅ | 690 | 13 | 53x |
| `context list` | ✅ | ✅ | ✅ | 701 | 14 | 50x |
| `context current` | ✅ | ✅ | ✅ | 694 | 14 | 49x |
| `context use` | ✅ | ✅ | ✅ | 702 | 13 | 54x |
| `context create` | ✅ | ✅ | ✅ | 719 | 14 | 51x |
| `context delete` | ✅ | ✅ | ✅ | 694 | 13 | 53x |
| `context rename` | ✅ | ✅ | ✅ | 693 | 13 | 53x |
| `disk add` | ✅ | ✅ | ✅ | 694 | 13 | 53x |
| `ip check` | ✅ | ✅ | ✅ | 706 | 13 | 54x |
| `web start` | ✅ | ✅ | ✅ | 692 | 13 | 53x |
| `web stop` | ✅ | ✅ | ✅ | 696 | 13 | 53x |
| `costs dashboard` | ✅ | ✅ | ✅ | 720 | 13 | 55x |
| `costs history` | ✅ | ✅ | ✅ | 696 | 13 | 53x |
| `costs budget` | ✅ | ✅ | ✅ | 691 | 13 | 53x |
| `costs recommend` | ✅ | ✅ | ✅ | 691 | 13 | 53x |
| `costs actions` | ✅ | ✅ | ✅ | 700 | 13 | 53x |
| `github-runner enable` | ✅ | ✅ | ✅ | 710 | 14 | 50x |
| `github-runner disable` | ✅ | ✅ | ✅ | 694 | 14 | 49x |
| `github-runner status` | ✅ | ✅ | ✅ | 703 | 13 | 54x |
| `github-runner scale` | ✅ | ✅ | ✅ | 701 | 13 | 53x |
| `doit deploy` | ✅ | ✅ | ✅ | 696 | 14 | 49x |
| `sessions save` | ✅ | ✅ | ✅ | 700 | 14 | 50x |
| `sessions list` | ✅ | ✅ | ✅ | 704 | 13 | 54x |
| `sessions load` | ✅ | ✅ | ✅ | 706 | 13 | 54x |
| `sessions delete` | ✅ | ❌ | ✅ | 701 | 13 | 53x |
| `bastion list` | ✅ | ✅ | ✅ | 710 | 14 | 50x |
| `bastion status` | ✅ | ✅ | ✅ | 704 | 14 | 50x |
| `bastion configure` | ✅ | ✅ | ✅ | 693 | 14 | 49x |
| `completions bash` | ✅ | ❌ | ✅ | 715 | 13 | 55x |

## Summary

- **Total commands tested**: 102
- **Python passing**: 93 / 102
- **Rust passing**: 102 / 102
- **With agentic tests**: 102 / 102
