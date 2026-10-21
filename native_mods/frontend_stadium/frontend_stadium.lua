-- Server16 frontend stadium v1. Only stadium index zero is the FE panorama.
Server16FrontendRoutes = Server16FrontendRoutes or {}

function Server16FrontendReadRoute(slot)
    if slot ~= 176 and slot ~= 261 then return nil end
    local routefile = "data/fifarna/lua/assets/server16_frontend_" .. slot .. ".lua"
    local ok = pcall(function()
        local script = gSportsRNA:LoadScriptAsync(routefile)
        gSportsRNA:LoadScriptAsyncComplete(script)
    end)
    local route = Server16FrontendRoutes[slot]
    if not ok or type(route) ~= "table" or type(route.model) ~= "string" then return nil end
    return route
end

function Server16FrontendUpdate(idx)
    local stadium = db.stadium[idx]
    stadium.server16Frontend = nil
    if idx ~= 0 then return end
    local route = Server16FrontendReadRoute(stadium.stadiumID)
    if not route then return end
    stadium.server16Frontend = route
    stadium.homeKitTeamID = route.team
    stadium.homeTeamID = route.team
    stadium.homeTeamIDasset = route.team
    stadium.homeTeamAssetId = route.team
    stadium.homeBannerId = route.team
end

function Server16FrontendModel(idx)
    local route = db.stadium[idx].server16Frontend
    if route then return route.model .. ";" end
    return ""
end

function Server16FrontendTexture(idx)
    local stadium = db.stadium[idx]
    local route = stadium.server16Frontend
    if route then
        if stadium.lightType == 3 then return route.night .. ";" end
        return route.day .. ";"
    end
    return ""
end

function Server16FrontendCrowdUpdate(idx)
    if idx ~= 0 then return end
    local native = gSportsRNA:GetTable("wvStadium", idx)
    local slot = gSportsRNA:GetInt(native, "stadID")
    local route = Server16FrontendReadRoute(slot)
    db.crowd[idx].server16Frontend = nil
    if type(route) ~= "table" then return end
    local crowd = db.crowd[idx]
    crowd.server16Frontend = route
    crowd.stadiumID = slot
    crowd.homeTeamID = route.team
    crowd.homeKitTeamID = route.team
    crowd.homeTeamIDseat = route.team
end

function Server16FrontendChair(idx)
    local route = db.crowd[idx].server16Frontend
    if route and type(route.chairs) == "string" and route.chairs ~= "" then return route.chairs .. ";" end
    return ""
end
