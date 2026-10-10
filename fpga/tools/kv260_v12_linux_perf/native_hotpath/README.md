# Native prepare/verify helper（仅Host准备）

这四个源文件实现普通64-bit进程内存上的完整poison、A/B输入copy、INT16全比较和输出Guard检查。没有transport、ioctl、DMA allocator、CSR访问、timer/boot/Cache控制；不是完整Linux driver或板测。`test_hotpath.py`通过`ctypes.CDLL`调用C ABI，调用期间释放GIL；禁止改成`PyDLL`。所有对象/映射须由调用者保持存活，无Python callback。[ctypes依据](https://docs.python.org/3.12/library/ctypes.html)。

`hotpath.h`固定14份只读span：共享weights/bias/frac/LUT、A low/full、B low/full、A三Golden、B三Golden。长度分别为10075/1944/486/8194、两组38160/5495040、两组三输出38160/5495040/5495040B。输出span和copy模式的活动输入span必须有前后64B保护区。每个span同时提供allocation长度、payload offset和长度，检查整数加法溢出、界限、2B对齐、保护区及只读/写区/元数据的虚拟地址别名；只读span的整个allocation（含其padding/guard）均受覆盖保护。各span必须描述不相交的真实区域；同一大arena可由backend提供经过证明的独立suballocation区域，不能每项都冒称整个arena。参数失败不触碰payload或receipt。冻结Q14按little-endian读取，编译时拒绝已知big-endian目标。

`kv_hp_validate_poison`在计时窗外扫描六份Golden，确认指定INT16 poison不在任何Golden中；成功实际检查11,028,240标量。`kv_hp_prepare`对三个完整输出逐word写poison，copy模式从真实kind对应的immutable源复制38160+5495040B；回执只有完成实际操作后才计数。preloaded模式不复制输入，仅由未来backend选择A/B的已初始化设备输入。默认`0xA5A5`；实际backend必须先核六Golden独立SHA并调用poison验证，调用者不能省略该前置条件。

`kv_hp_verify`先检查六个64B输出Guard，再逐INT16比较选定A/B全部三输出。成功须实际检查5,514,120标量和384B Guard；首个异常立即返回，失败receipt只记录真正已访问的数量和首错位置，不能包装成完整PASS。错误返回之后真实binding须立即请求kernel STOP；此helper自身不能latch STOP或撤销DMA。现有ring的verify异常路径会调用`_fail`；binding应保留原始失败receipt并raise，禁止只回报零差异字典。

这里只验证虚拟地址界限与不相交。不同VA可能映射同一物理/DMA页，甚至设备可见映射不同；真实kernel backend必须证明allocation ID、物理页/DMA domain和owner，保证copy不会覆盖任何未验证帧/其它consumer。prepare须取得FREE槽并转为producer owner；verify须取得OUTPUT_READY/VALIDATING槽，确认该槽全部producer完成且CPU可见，校验成功后才转FREE，其它独立槽可以继续生产。两种调用都必须满足本槽的DMA/Cache所有权与同步，C代码不替代DMA barrier/sync，也不能保证调用者谎报的allocation长度或未映射指针可访问。只读asset的完整身份、模型及所有共享Guard由backend在开始/结束独立SHA/audit，本helper没有`SHA_OK`字段。并行producer/validator必须使用不相交且分别持有的slot；固定3槽/A-B翻转由ring核心负责。

每帧11,028,240B full poison、5,533,200B实际copy（仅copy阶段）以及检查时间必须保留在连续wall-clock；不能扣除后把service窗口拼成持续FPS。Host memcpy到Golden模拟输出只用于测试native比较，不是模块计算。

Host构建与验证（在仓库根运行；64-bit Windows MinGW GCC放入PATH，产物只放忽略的outputs）：

```powershell
New-Item -ItemType Directory -Force outputs/kv260_v12_native | Out-Null
gcc -std=c11 -O2 -Wall -Wextra -Werror -fno-strict-aliasing -shared '-Wl,--no-insert-timestamp' '-Wl,--image-base,0x180000000' fpga/tools/kv260_v12_linux_perf/native_hotpath/hotpath.c -o outputs/kv260_v12_native/hotpath_host.dll
$env:KV_HP_LIBRARY = (Resolve-Path outputs/kv260_v12_native/hotpath_host.dll).Path
Remove-Item Env:KV_HP_S1_PLAN -ErrorAction SilentlyContinue
python -B -m unittest discover -s fpga/tools/kv260_v12_linux_perf/native_hotpath -p test_hotpath.py -v
```

上面默认运行10项普通Host RAM测试，未提供真实数据时1项可选S1测试显示skip。不要把skip写成S1数据校验PASS。Linux AArch64构建使用PATH中的交叉编译器；可改用与目标运行环境匹配的编译器名称：

```sh
mkdir -p outputs/kv260_v12_native
aarch64-linux-gnu-gcc -std=c11 -O2 -Wall -Wextra -Werror -fno-strict-aliasing -fPIC -shared -Wl,--no-undefined fpga/tools/kv260_v12_linux_perf/native_hotpath/hotpath.c -o outputs/kv260_v12_native/libkv_hotpath.so
```

可选的真实S1数据校验通过 `KV_HP_S1_PLAN` 显式传入单独交付的本地JSON，不依赖未提交的历史candidate目录。JSON顶层须含`assets`，以`A/weights_int8.bin`等asset名索引；每项提供接收者实际数据文件的`path`与权威`sha256`。14个具体asset名和顺序见 `test_optional_real_S1_assets_are_SHA_bound_and_compared_in_Host_RAM`。接收者应在本地重写路径并核对交接manifest；本机路径和大数据文件不进入Git。未设此变量默认skip，不会自动寻找或下载数据。需要启用时，设置变量后重新运行同一测试命令。

环境变量仅指向显式Host文件；库以绝对路径加载。Linux AArch64 `.so`只供未来已批准的Linux进程loader，不用于U-Boot go/bootelf/JTAG。Host DLL测试涵盖真实full-size RAM、每word poison和copy、完整raw compare、部分stale、错Golden、Golden含poison、两端Guard、长度/溢出/对齐、output/immutable/copy/receipt别名、CDLL线程进展；可选S1测试先在Python独立核14源SHA，再复制到Host RAM。它不证实真实AArch64并发、DMA一致性、kernel STOP或30 FPS。
