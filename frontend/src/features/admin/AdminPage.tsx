import { useSearchParams } from 'react-router'

import PageHeader from '../../components/PageHeader'
import InvitesTab from './InvitesTab'
import OverviewTab from './OverviewTab'
import TeamsTab from './TeamsTab'
import UsersTab from './UsersTab'

const TABS = [
  { id: 'overview', label: 'Overview', Component: OverviewTab },
  { id: 'teams', label: 'Teams', Component: TeamsTab },
  { id: 'users', label: 'Users', Component: UsersTab },
  { id: 'invites', label: 'Invites', Component: InvitesTab },
] as const

type TabId = (typeof TABS)[number]['id']

function isTabId(value: string | null): value is TabId {
  return TABS.some((tab) => tab.id === value)
}

export default function AdminPage() {
  // The tab lives in the URL (?tab=users) so it survives reloads and can be linked.
  const [searchParams, setSearchParams] = useSearchParams()
  const param = searchParams.get('tab')
  const active: TabId = isTabId(param) ? param : 'overview'
  const { Component } = TABS.find((tab) => tab.id === active) ?? TABS[0]

  return (
    <>
      <PageHeader title="Admin" description="Teams, users and invites." />
      <div className="mb-6 overflow-x-auto">
        <div role="tablist" aria-label="Admin sections" className="tabs tabs-box w-max min-w-full">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`admin-tab-${tab.id}`}
              aria-selected={tab.id === active}
              aria-controls="admin-tabpanel"
              className={`tab flex-1 ${tab.id === active ? 'tab-active' : ''}`}
              onClick={() => setSearchParams(tab.id === 'overview' ? {} : { tab: tab.id })}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <section id="admin-tabpanel" role="tabpanel" aria-labelledby={`admin-tab-${active}`}>
        <Component />
      </section>
    </>
  )
}
