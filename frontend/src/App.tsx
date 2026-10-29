import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { HomePage } from './pages/HomePage'
import { InvestigationPage } from './pages/InvestigationPage'
import { NewInvestigationPage } from './pages/NewInvestigationPage'
import { SettingsPage } from './pages/SettingsPage'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/investigate" element={<NewInvestigationPage />} />
        <Route path="/investigations/:id" element={<InvestigationPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<p>Page not found.</p>} />
      </Routes>
    </Layout>
  )
}
