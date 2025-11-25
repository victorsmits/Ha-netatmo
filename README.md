# 🏠 Netatmo Modular - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/victorsmits/netatmo-modular-ha.svg)](https://github.com/victorsmits/netatmo-modular-ha/releases)
[![License](https://img.shields.io/github/license/victorsmits/netatmo-modular-ha.svg)](LICENSE)

Une intégration Home Assistant **non officielle** pour Netatmo avec découverte dynamique des entités.

**Compatible Cloudflare Tunnel / Reverse Proxy** ✅

## ✨ Fonctionnalités

- 🔄 **Découverte automatique** des homes, pièces et modules Netatmo
- 🌡️ **Entités Climate** pour chaque pièce avec thermostat
- 📊 **Sensors** pour température, batterie, signal, état chaudière
- 🔐 **OAuth2** avec support URL externe (Cloudflare, Nginx, etc.)
- 💾 **Stockage sécurisé** des tokens (persistant aux reboots)
- 🎨 **Interface de configuration** via l'UI Home Assistant
- 🇫🇷 **Traduction française** incluse

## 📋 Prérequis

1. Un compte Netatmo avec des équipements de chauffage (thermostats, vannes, etc.)
2. Une application Netatmo créée sur [dev.netatmo.com](https://dev.netatmo.com/apps)
3. HACS installé sur votre Home Assistant
4. (Optionnel) Un domaine externe type `https://ha.exemple.com` (Cloudflare, DuckDNS, etc.)

## 🚀 Installation

### Via HACS (Recommandé)

1. Ouvrez HACS dans Home Assistant
2. Cliquez sur les 3 points en haut à droite → **Dépôts personnalisés**
3. Ajoutez :
   - URL : `https://github.com/victorsmits/netatmo-modular-ha`
   - Catégorie : `Integration`
4. Cliquez sur **Ajouter**
5. Cherchez "Netatmo Modular" dans HACS
6. Cliquez sur **Télécharger**
7. Redémarrez Home Assistant

### Installation manuelle

1. Téléchargez le dossier `custom_components/netatmo_modular`
2. Copiez-le dans `/config/custom_components/`
3. Redémarrez Home Assistant

## ⚙️ Configuration

### 1. Créer une application Netatmo

1. Allez sur [dev.netatmo.com/apps](https://dev.netatmo.com/apps)
2. Créez une nouvelle application
3. **IMPORTANT** - Configurez le **Redirect URI** selon votre setup :

   **Si vous utilisez Cloudflare Tunnel ou un domaine externe :**
   ```
   https://ha.votredomaine.com/auth/external/callback
   ```
   
   **Si vous n'avez pas de domaine externe :**
   ```
   https://my.home-assistant.io/redirect/oauth
   ```

4. Notez le **Client ID** et **Client Secret**

### 2. Ajouter l'intégration

1. Dans Home Assistant : **Paramètres** → **Appareils et services** → **Ajouter une intégration**
2. Cherchez "Netatmo Modular"
3. Remplissez :
   - **Client ID** : votre client ID Netatmo
   - **Client Secret** : votre client secret Netatmo
   - **URL externe** : `https://ha.votredomaine.com` (ou laissez vide si pas de domaine)
4. Cliquez sur **Suivant**
5. Un lien d'autorisation Netatmo s'affiche → Cliquez dessus
6. Connectez-vous à Netatmo et autorisez l'application
7. Vous serez redirigé vers une URL contenant `?code=XXXXX`
8. **Copiez le code** (la partie après `code=` et avant `&`)
9. Collez-le dans le champ "Code d'autorisation"
10. C'est fait ! 🎉

### Exemple avec Cloudflare

```
Configuration Netatmo :
  Redirect URI: https://ha.victorsmits.com/auth/external/callback

Configuration Intégration :
  Client ID: 692xxxxxxxxxxxxx
  Client Secret: qafyexxxxxxxxxxxxxxx
  URL externe: https://ha.victorsmits.com

Après autorisation, URL de redirection :
  https://ha.victorsmits.com/auth/external/callback?code=abc123xyz&state=...
  
→ Copiez "abc123xyz" et collez-le dans l'intégration
```

## 🎛️ Entités créées

### Climate (par pièce)

| Entité | Description |
|--------|-------------|
| `climate.netatmo_modular_climate_[room_id]` | Thermostat de la pièce |

**Fonctionnalités :**
- Modes HVAC : Auto, Heat, Off
- Presets : Comfort, Eco, Frost Guard, Away, Schedule
- Réglage de température

### Sensors (par pièce)

| Entité | Description |
|--------|-------------|
| `sensor.[room]_temperature` | Température mesurée |
| `sensor.[room]_target_temperature` | Température cible |
| `sensor.[room]_heating_power` | Puissance de chauffe demandée |
| `sensor.[room]_setpoint_mode` | Mode de consigne actuel |

### Sensors (par module)

| Entité | Description |
|--------|-------------|
| `sensor.[module]_battery_level` | Niveau de batterie (%) |
| `sensor.[module]_battery_state` | État de la batterie |
| `sensor.[module]_rf_strength` | Force du signal RF |
| `sensor.[module]_wifi_strength` | Force du signal WiFi |
| `sensor.[module]_boiler_status` | État de la chaudière |
| `sensor.[module]_reachable` | Module joignable |

### Sensors (par home)

| Entité | Description |
|--------|-------------|
| `sensor.[home]_therm_mode` | Mode global du thermostat |

## 🔧 Exemples d'automatisation

### Passer en mode Eco la nuit

```yaml
automation:
  - alias: "Chauffage - Mode Eco la nuit"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: climate.set_preset_mode
        target:
          entity_id: climate.netatmo_modular_climate_123456789
        data:
          preset_mode: eco
```

### Alerter si batterie faible

```yaml
automation:
  - alias: "Netatmo - Alerte batterie faible"
    trigger:
      - platform: numeric_state
        entity_id: sensor.vanne_chambre_battery_level
        below: 20
    action:
      - service: notify.mobile_app
        data:
          title: "🔋 Batterie faible"
          message: "La vanne de la chambre a une batterie faible ({{ states('sensor.vanne_chambre_battery_level') }}%)"
```

### Carte Lovelace

```yaml
type: thermostat
entity: climate.netatmo_modular_climate_123456789
features:
  - type: climate-hvac-modes
    hvac_modes:
      - auto
      - heat
      - off
  - type: climate-preset-modes
    preset_modes:
      - comfort
      - eco
      - frost_guard
      - away
      - schedule
```

## 🐛 Dépannage

### L'intégration ne se connecte pas

1. Vérifiez que le Redirect URI est correct dans votre app Netatmo
2. Vérifiez que les scopes incluent `read_thermostat` et `write_thermostat`
3. Consultez les logs : **Paramètres** → **Système** → **Journaux**

### Les entités ne sont pas créées

1. Vérifiez que vous avez des équipements de chauffage dans votre compte Netatmo
2. L'intégration ne crée des entités climate que pour les pièces avec des modules

### Erreur "invalid_grant"

Le refresh token a expiré. Supprimez l'intégration et reconfigurez-la.

### Voir les logs détaillés

Ajoutez dans `configuration.yaml` :

```yaml
logger:
  default: info
  logs:
    custom_components.netatmo_modular: debug
```

## 📝 Changelog

### v1.0.0
- 🎉 Version initiale
- ✅ Découverte dynamique des homes, pièces et modules
- ✅ Entités Climate avec presets
- ✅ Sensors pour température, batterie, signal
- ✅ OAuth2 avec refresh automatique
- ✅ Traductions FR/EN

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une PR.

## 📄 License

MIT License - Voir [LICENSE](LICENSE)

## ⚠️ Disclaimer

Cette intégration n'est pas officielle et n'est pas affiliée à Netatmo.
