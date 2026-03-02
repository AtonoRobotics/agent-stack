import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { NavContext } from './contexts/NavContext'
import { AuthContext } from './contexts/AuthContext'
import { authFetch } from './utils/authFetch'
import { useWebSocket } from './hooks/useWebSocket'
import { Sidebar } from './components/Sidebar'
import { MobileNav } from './components/MobileNav'
import { LoginPage } from './pages/LoginPage'
import { LabOverviewPage } from './pages/LabOverviewPage'
import { FleetPage } from './pages/FleetPage'
import { RobotDetailPage } from './pages/RobotDetailPage'
import { CockpitPage } from './pages/CockpitPage'
import { SimulationsPage } from './pages/SimulationsPage'
import { TrainingPage } from './pages/TrainingPage'
import { AgentsPage } from './pages/AgentsPage'
import { DemosPage } from './pages/DemosPage'
import { MCAgentsPage } from './pages/MCAgentsPage'
import { WorkflowsPage } from './pages/WorkflowsPage'
import { RegistryPage } from './pages/RegistryPage'
import { InfraPage } from './pages/InfraPage'

var e = React.createElement;

function App() {
  // Auth state
  var tokenState = useState(localStorage.getItem('mc_token'));
  var token = tokenState[0];
  var setToken = tokenState[1];
  var userState = useState(function() {
    try { return JSON.parse(localStorage.getItem('mc_user')); } catch(ex) { return null; }
  });
  var user = userState[0];
  var setUser = userState[1];

  function handleLogin(userData, tokenStr) {
    setUser(userData);
    setToken(tokenStr);
  }

  function handleLogout() {
    authFetch('/api/auth/logout', { method: 'POST' }).catch(function() {});
    localStorage.removeItem('mc_token');
    localStorage.removeItem('mc_user');
    setToken(null);
    setUser(null);
  }

  // All hooks must be called unconditionally (Rules of Hooks)
  var wsStatus = useWebSocket();
  var pageState = useState('lab');
  var currentPage = pageState[0];
  var setCurrentPage = pageState[1];
  var paramsState = useState({});
  var navParams = paramsState[0];
  var setNavParams = paramsState[1];

  // Splash screen state
  var splashState = useState(true);
  var showSplash = splashState[0];
  var setShowSplash = splashState[1];

  useEffect(function() {
    var timer = setTimeout(function() { setShowSplash(false); }, 2000);
    return function() { clearTimeout(timer); };
  }, []);

  var navigate = useCallback(function(page, params) {
    setCurrentPage(page);
    setNavParams(params || {});
  }, []);

  var authContextValue = useMemo(function() {
    return { user: user, token: token, logout: handleLogout };
  }, [user, token]);

  var navContextValue = useMemo(function() {
    return { page: currentPage, params: navParams, navigate: navigate };
  }, [currentPage, navParams, navigate]);

  // If no token, show login
  if (!token) {
    return e(LoginPage, { onLogin: handleLogin });
  }

  // Splash screen
  if (showSplash) {
    return e('div', {
      style: {
        position: 'fixed', inset: 0, background: '#0F0F0F', zIndex: 9999,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        animation: 'fadeIn 0.3s ease'
      }
    },
      e('div', {
        style: {
          fontSize: '60px', color: '#E8A020', fontStyle: 'italic',
          fontFamily: "'Times New Roman', serif", lineHeight: 1, marginBottom: '16px'
        }
      }, '\u03B1'),
      e('div', {
        style: {
          fontSize: '14px', fontWeight: 600, letterSpacing: '0.2em',
          color: '#E0E0E0', textTransform: 'uppercase', fontFamily: 'Inter, sans-serif'
        }
      }, 'MISSION CONTROL'),
      e('div', {
        style: {
          fontSize: '11px', color: '#808080', letterSpacing: '0.1em',
          textTransform: 'uppercase', marginTop: '6px'
        }
      }, 'by Alpha')
    );
  }

  var pageElement = null;
  if (currentPage === 'lab') pageElement = e(LabOverviewPage);
  else if (currentPage === 'fleet') pageElement = e(FleetPage);
  else if (currentPage === 'robot') pageElement = e(RobotDetailPage);
  else if (currentPage === 'cockpit') pageElement = e(CockpitPage);
  else if (currentPage === 'simulations') pageElement = e(SimulationsPage);
  else if (currentPage === 'training') pageElement = e(TrainingPage);
  else if (currentPage === 'agents') pageElement = e(AgentsPage);
  else if (currentPage === 'demos') pageElement = e(DemosPage);
  else if (currentPage === 'mc-agents') pageElement = e(MCAgentsPage);
  else if (currentPage === 'workflows') pageElement = e(WorkflowsPage);
  else if (currentPage === 'registry') pageElement = e(RegistryPage);
  else if (currentPage === 'infra') pageElement = e(InfraPage);

  return e(AuthContext.Provider, { value: authContextValue },
    e(NavContext.Provider, { value: navContextValue },
      e('div', { className: 'layout' },
        e(Sidebar, { wsStatus: wsStatus }),
        e('main', { className: 'main-content' }, pageElement),
        e(MobileNav)
      )
    )
  );
}

export { App }
