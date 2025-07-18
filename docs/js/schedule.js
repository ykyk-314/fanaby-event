function showTalentSchedule(talentID) {
  fetch('../data/talent_schedules.json')
    .then(res => res.json())
    .then(data => {
      const events = data.filter(e => e.TalentID === talentID);
      if (events.length === 0) {
        document.getElementById('schedule-list').innerHTML = 'スケジュールがありません。';
        return;
      }
      // タレント名
      document.getElementById('talent-name').textContent = events[0].TalentName + ' スケジュール';

      // 月ごとにまとめて表示
      const byMonth = {};
      events.forEach(e => {
        const ym = e.EventDate.substring(0, 7);
        if (!byMonth[ym]) byMonth[ym] = [];
        byMonth[ym].push(e);
      });

      let html = '';
      Object.keys(byMonth).sort().forEach(ym => {
        html += `<h2>${ym}</h2><table border="1" style="border-collapse:collapse"><tr>
          <th>日付</th><th>開始</th><th>公演名</th><th>会場</th><th>出演者</th><th>チケット</th>
        </tr>`;
        byMonth[ym].forEach(ev => {
          html += `<tr>
            <td>${ev.EventDate}</td>
            <td>${ev.EventStartTime}</td>
            <td>${ev.EventTitle}</td>
            <td>${ev.TheaterVenue}</td>
            <td>${ev.EventMembers}</td>
            <td>${ev.TicketLink ? `<a href="${ev.TicketLink}" target="_blank">リンク</a>` : ''}</td>
          </tr>`;
        });
        html += '</table>';
      });
      document.getElementById('schedule-list').innerHTML = html;
    });
}
