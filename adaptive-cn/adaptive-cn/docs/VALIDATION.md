# Build validation

Validated in the build environment:

- 8 automated tests passed (`python -m unittest discover -s tests -v`).
- JavaScript syntax passed (`node --check web/app.js`).
- All Python modules compile.
- Training produced a model and held-out synthetic metrics.
- 60 deterministic simulation experiments completed across four scenarios, three modes, and five seeds.
- Backend integration tests served dashboard assets, rejected unauthenticated agent access, accepted measured telemetry/probes, exported CSV, and rejected invalid controls.
- Socket-based mocked-switch test covered OpenFlow handshake, echo reply, barrier reply, and port-counter parsing. FlowMod wire offsets and lengths were checked separately.

Not validated here:

- Mininet/Open vSwitch forwarding and iperf3 experiments: those Linux services were not available.
- Browser rendering and click-through: Playwright was present but no Chromium executable was installed. JavaScript syntax and HTTP asset delivery passed; visual layout still needs checking in your browser.
- Docker image build and Windows batch launch on a Windows computer.
- Predictive accuracy on real network traffic. The bundled model uses synthetic data.

Before your presentation, follow MININET_GUIDE.md and verify flow tables, packet connectivity, route transitions, and measured summaries. Record failures as well as improvements.
