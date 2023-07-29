using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace stocksearcher
{
    internal class StockNode
    {
        // 시간타임
        public List<long?> timestamp { get; set; }
        // 시가
        public List<long?> open { get; set; }
        // 최고가
        public List<long?> high { get; set; }
        // 최저가
        public List<long?> low { get; set; }
        // 종가
        public List<long?> close { get; set; }
        // 거래량
        public List<long?> volume { get; set; }
    }
}
