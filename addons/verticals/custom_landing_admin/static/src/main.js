/** @odoo-module **/

import { App, Component, mount, whenReady, xml, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";

import { createLandingRouter } from "./services/landing_router";
import { OnboardingPipeline } from "./components/onboarding_pipeline/onboarding_pipeline";
import { JourneyWorkspace } from "./components/journey_workspace/journey_workspace";
import { VpsConsole } from "./components/vps_console/vps_console";
import { MonitoringDashboard } from "./components/monitoring_dashboard/monitoring_dashboard";
import { ModuleDeployConsole } from "./components/module_deploy_console/module_deploy_console";

/**
 * Root component — renders the persistent chrome (top-nav + sidebar)
 * and swaps the central panel based on the current route.
 */
class LandingApp extends Component {
    static template = "custom_landing_admin.LandingApp";
    static components = {
        OnboardingPipeline,
        JourneyWorkspace,
        VpsConsole,
        MonitoringDashboard,
        ModuleDeployConsole,
    };
    static props = {};

    setup() {
        this.router = createLandingRouter();
        this.state = useState({
            user: (window.__landing_admin__ || {}).user || {
                name: "User",
                login: "",
            },
        });
    }

    get route() {
        return this.router.current;
    }

    nav(path) {
        this.router.navigate(path);
    }

    isActive(name) {
        return this.router.current.name === name ? "active" : "";
    }
}

// Inline template so the root component does not depend on a separate
// XML file (which would require it to be picked up by the asset
// bundle's QWeb parser). All sub-components ship their own .xml files.
LandingApp.template = xml/* xml */ `
<div class="o_landing_app">
    <header class="o_landing_topnav">
        <div class="o_landing_brand">
            <i class="fa fa-cubes"/>
            <span>Platform Landing</span>
        </div>
        <div class="o_landing_topnav_spacer"/>
        <div class="o_landing_user">
            <i class="fa fa-user-circle"/>
            <span t-esc="state.user.name"/>
        </div>
    </header>
    <div class="o_landing_body">
        <aside class="o_landing_sidebar">
            <ul>
                <li t-att-class="isActive('pipeline')"
                    t-on-click="() => this.nav('/pipeline')">
                    <i class="fa fa-columns"/> Onboarding Pipeline
                </li>
                <li t-att-class="isActive('vps')"
                    t-on-click="() => this.nav('/vps')">
                    <i class="fa fa-server"/> VPS Console
                </li>
                <li t-att-class="isActive('monitoring')"
                    t-on-click="() => this.nav('/monitoring')">
                    <i class="fa fa-heartbeat"/> Monitoring
                </li>
                <li t-att-class="isActive('modules')"
                    t-on-click="() => this.nav('/modules')">
                    <i class="fa fa-puzzle-piece"/> Module Deploy
                </li>
            </ul>
        </aside>
        <main class="o_landing_main">
            <t t-if="route.name === 'pipeline'">
                <OnboardingPipeline onOpenJourney="(id) => this.nav('/journey/' + id)"/>
            </t>
            <t t-elif="route.name === 'journey'">
                <JourneyWorkspace journeyId="route.params.id"
                                  onBack="() => this.nav('/pipeline')"/>
            </t>
            <t t-elif="route.name === 'vps'">
                <VpsConsole/>
            </t>
            <t t-elif="route.name === 'monitoring'">
                <MonitoringDashboard/>
            </t>
            <t t-elif="route.name === 'modules'">
                <ModuleDeployConsole/>
            </t>
            <t t-else="">
                <div class="o_landing_notfound">
                    <h2>Page not found</h2>
                    <p>The route
                        <code t-esc="route.name"/>
                        does not match any known view.
                    </p>
                </div>
            </t>
        </main>
    </div>
</div>
`;

whenReady(() => {
    const root = document.getElementById("landing_admin_root");
    if (!root) {
        return;
    }
    // Clear the boot placeholder.
    root.innerHTML = "";
    const app = new App(LandingApp, {
        name: "LandingAdmin",
        templates,
        env: { },
        dev: false,
        translatableAttributes: ["data-tooltip"],
    });
    app.mount(root);
});

export { LandingApp };
// ``mount`` re-export is intentional — handy for tests / devtools.
export { mount };
