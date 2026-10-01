import { createRouter, createWebHistory } from 'vue-router'

import Dashboard from '@/views/Dashboard.vue'
const Windfarm = () => import('@/views/windfarm/index.vue')
const Turbine = () => import('@/views/turbine/index.vue')
const Blade = () => import('@/views/blade/index.vue')
const Gearbox = () => import('@/views/gearbox/index.vue')
const Generator = () => import('@/views/generator/index.vue')
const Pitch = () => import('@/views/pitch/index.vue')
const Yaw = () => import('@/views/yaw/index.vue')
const Metmast = () => import('@/views/metmast/index.vue')
const Collector = () => import('@/views/collector/index.vue')
const Substation = () => import('@/views/substation/index.vue')
const Forecast = () => import('@/views/forecast/index.vue')
const Vibration = () => import('@/views/vibration/index.vue')
const Defect = () => import('@/views/defect/index.vue')
const Maintjob = () => import('@/views/maintjob/index.vue')
const Spare = () => import('@/views/spare/index.vue')
const Patrol = () => import('@/views/patrol/index.vue')
const Accept = () => import('@/views/accept/index.vue')
const Settle = () => import('@/views/settle/index.vue')
const Seawindow = () => import('@/views/seawindow/index.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: Dashboard },
    { path: '/windfarm', name: 'windfarm', component: Windfarm },
    { path: '/turbine', name: 'turbine', component: Turbine },
    { path: '/blade', name: 'blade', component: Blade },
    { path: '/gearbox', name: 'gearbox', component: Gearbox },
    { path: '/generator', name: 'generator', component: Generator },
    { path: '/pitch', name: 'pitch', component: Pitch },
    { path: '/yaw', name: 'yaw', component: Yaw },
    { path: '/metmast', name: 'metmast', component: Metmast },
    { path: '/collector', name: 'collector', component: Collector },
    { path: '/substation', name: 'substation', component: Substation },
    { path: '/forecast', name: 'forecast', component: Forecast },
    { path: '/vibration', name: 'vibration', component: Vibration },
    { path: '/defect', name: 'defect', component: Defect },
    { path: '/maintjob', name: 'maintjob', component: Maintjob },
    { path: '/spare', name: 'spare', component: Spare },
    { path: '/patrol', name: 'patrol', component: Patrol },
    { path: '/accept', name: 'accept', component: Accept },
    { path: '/settle', name: 'settle', component: Settle },
    { path: '/seawindow', name: 'seawindow', component: Seawindow },
  ],
})

export default router
