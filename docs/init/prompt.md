ORBIT-OS(Operating-system Resource Balancing & Intelligent Task placement) We build a resource-management simulator that treats CPU, GPU, RAM, VRAM, and storage as interconnected rather than independent resources, allowing contention in one resource to cascade into performance degradation or failures in another. The system lets us reproduce, rewind, and compare different resource-management and recovery policies against the exact same induced workload scenario.

Project: ORBIT-OS — Heterogeneous Cross-Resource OS Simulator

Instead of making a normal CPU scheduling visualizer, we will build an integrated OS simulation environment where CPU scheduling, memory management, storage I/O and deadlock management interact with each other.

The interesting part is that we model a modern heterogeneous machine with CPU + GPU + RAM + VRAM + storage and different workload classes such as:

🎮 Interactive / latency-sensitive workload
🤖 AI/LLM workload
💻 Developer/compilation workload
⚙️ Background workload

For each task, NEXUS can estimate whether it should execute on CPU, GPU, or a simulated CPU-GPU hybrid path, considering the task's characteristics, current CPU/GPU queues, memory/VRAM pressure and transfer overhead.

The system also records the complete resource/event state. If a workload causes a resource cascade or performance crisis, we can checkpoint → rewind → change the OS policy → replay the exact same workload and compare the results.

So instead of asking only “Which CPU scheduling algorithm is better?”, our project asks:

“How should an OS manage heterogeneous CPU/GPU/memory/storage resources when different types of workloads with conflicting performance requirements run simultaneously on one machine?”

Classical OS algorithms will remain the foundation, while our research layer adds workload-aware resource placement, cross-resource interference analysis and deterministic replay/counterfactual experimentation.