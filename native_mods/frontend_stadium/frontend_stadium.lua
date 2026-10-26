-- Server16 frontend stadium v1. Only stadium index zero is the FE panorama.
Server16FrontendRoutes = Server16FrontendRoutes or {}
Server16MatchRoutes = Server16MatchRoutes or {}

function Server16MatchUpdate(idx)
    local stadium = db.stadium[idx]
    stadium.server16Match = nil
    if idx == 0 then return end
    local slot = stadium.stadiumID
    if slot ~= 176 and slot ~= 261 then return end
    -- Never accept the previous Lua table if loading this fixture fails.
    Server16MatchRoutes[slot] = nil
    local ok = pcall(function()
        local script = gSportsRNA:LoadScriptAsync("data/fifarna/lua/assets/server16_match_" .. slot .. ".lua")
        gSportsRNA:LoadScriptAsyncComplete(script)
    end)
    local route = Server16MatchRoutes[slot]
    if not ok or type(route) ~= "table" or route.home ~= stadium.homeKitTeamID or route.away ~= stadium.awayKitTeamID then return end
    if type(route.model) ~= "string" or type(route.day) ~= "string" or type(route.night) ~= "string" then return end
    stadium.server16Match = route
end

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
    Server16MatchUpdate(idx)
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
    local stadium = db.stadium[idx]
    local route = idx == 0 and stadium.server16Frontend or stadium.server16Match
    if route then return route.model .. ";" end
    return ""
end

function Server16FrontendTexture(idx)
    local stadium = db.stadium[idx]
    local route = idx == 0 and stadium.server16Frontend or stadium.server16Match
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
